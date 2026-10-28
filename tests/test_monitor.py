"""Offline tests of the original engine and the separate configuration layer."""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_iphone_duo as app
import configuration as cfg


def config():
    return {'version': 1, 'shop_url': 'https://www.apple.com/shop/', 'locations': ['10001'],
            'interval_minutes': 15, 'heartbeat_hour': None,
            'products': [{'part': 'ABCDELL/A', 'name': 'iPhone Example 512GB Black',
                          'url': 'https://www.apple.com/shop/buy-iphone/iphone-example'}],
            'stores': [{'id': 'R001', 'name': 'Example Store'}], 'ntfy': {'enabled': False}}


def payload(available=True, part='ABCDELL/A', name='iPhone Example 512GB Black', store='Example Store', nested=False):
    info = {part: {'pickupDisplay': 'available', 'storePickupQuote': 'Today',
                  'messageTypes': {'regular': {'storePickupProductTitle': name}}}} if available else {}
    pm = {'stores': [{'storeNumber': 'R001', 'storeName': store, 'partsAvailability': info}]}
    body = {'content': {'pickupMessage': pm}} if nested else {'PickupMessage': pm}
    return json.dumps({'body': body})


class EngineContractTests(unittest.TestCase):
    def test_core_control_flow_matches_original(self):
        tree=ast.parse(Path(app.__file__).read_text())
        nodes={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        for node in tree.body:
            if isinstance(node,ast.ClassDef) and node.name=='Monitor':
                nodes.update({'Monitor.'+n.name:n for n in node.body if isinstance(n,ast.FunctionDef)})
        class Canonical(ast.NodeTransformer):
            def visit_Constant(self,node):
                if isinstance(node.value,str):node.value='<message>'
                return node
            def visit_Name(self,node):
                if node.id=='now_rome':node.id='now_local'
                return node
            def visit_FunctionDef(self,node):
                self.generic_visit(node)
                node.body=[n for n in node.body if not(isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))]
                return node
        for line in Path(__file__).with_name('original_core.sha256').read_text().splitlines():
            key,expected=line.split()
            with self.subTest(function=key):
                actual=hashlib.sha256(ast.dump(Canonical().visit(nodes[key]),include_attributes=False).encode()).hexdigest()
                self.assertEqual(actual,expected,'Original control flow changed; translated messages are normalized for comparison.')

    def test_original_browser_headers_are_preserved_for_italy(self):
        self.assertIn('Safari/605.1.15',app.HEADERS['User-Agent'])
        self.assertEqual(app.HEADERS['X-Requested-With'],'XMLHttpRequest')
        self.assertIn('as_sfa=',app.HEADERS['Cookie'])


class EngineTests(unittest.TestCase):
    def setUp(self):
        patch.object(app.time,'sleep').start()
        patch.object(app,'network_ok',return_value=True).start()
        self.send=patch.object(app,'send_ntfy',return_value=True).start()
        self.logs=patch.object(app,'log').start()
        self.output=patch('sys.stdout',new=io.StringIO()).start()
        self.conf=config()
        self.profile=cfg.apply_configuration(app,self.conf)[0]
        cfg.apply_profile(app,self.profile)
        self.addCleanup(patch.stopall)

    def cycle(self,monitor,raw):
        with patch.object(monitor,'discover',return_value=['ABCDELL/A']),patch.object(app,'get_with_retry',return_value=raw):
            return monitor.cycle()

    def test_parser_reads_both_original_shapes(self):
        for nested in (False,True):
            result=app.parse_rows(payload(nested=nested),'ABCDELL/A')
            self.assertEqual(result,[('ABCDELL/A','iPhone Example 512GB Black','Example Store',True,'Today')])

    def test_parser_preserves_available_alternatives_from_apple(self):
        raw=payload(part='OTHERLL/A',name='iPhone Example 1TB Black')
        self.assertEqual(app.parse_rows(raw,'ABCDELL/A')[0][0],'OTHERLL/A')
        self.assertTrue(self.cycle(app.Monitor(),raw))
        self.assertIn('1TB Black',self.send.call_args.args[0])
        self.assertIn('Example Store',self.send.call_args.args[0])

    def test_both_postal_and_direct_store_requests_are_sent(self):
        monitor=app.Monitor()
        with patch.object(monitor,'discover',return_value=['ABCDELL/A']),patch.object(app,'get_with_retry',return_value=payload(False)) as get:
            self.assertTrue(monitor.cycle())
        urls=[call.args[0] for call in get.call_args_list]
        self.assertTrue(any('location=10001' in url and 'searchNearby=true' in url for url in urls))
        self.assertTrue(any('store=R001' in url for url in urls))

    def test_multiple_locations_are_all_retained(self):
        self.conf['locations']=['10001','10002']
        cfg.apply_configuration(app,self.conf);cfg.apply_profile(app,self.profile)
        monitor=app.Monitor()
        with patch.object(monitor,'discover',return_value=['ABCDELL/A']),patch.object(app,'get_with_retry',return_value=payload(False)) as get:
            monitor.cycle()
        self.assertEqual(get.call_count,3)

    def test_empty_parts_mean_no_availability_and_rearm_after_two_rounds(self):
        monitor=app.Monitor()
        self.cycle(monitor,payload())
        self.cycle(monitor,payload(False))
        self.assertEqual(list(monitor.seen.values()),[1])
        self.cycle(monitor,payload(False))
        self.assertEqual(monitor.seen,{})
        self.cycle(monitor,payload())
        self.assertEqual(self.send.call_count,2)
        self.assertTrue(any('No example available' in call.args[0] for call in self.logs.call_args_list))

    def test_different_family_and_unselected_store_are_ignored(self):
        for raw in (payload(name='iPhone Other 512GB'),payload(store='Different Store')):
            self.cycle(app.Monitor(),raw)
        self.send.assert_not_called()

    def test_three_failed_rounds_notify_and_recovery_notifies(self):
        monitor=app.Monitor()
        with patch.object(app,'network_ok',return_value=False):
            for _ in range(4):self.assertFalse(monitor.cycle())
        self.assertEqual(self.send.call_count,1)
        self.assertIn('error',self.send.call_args.args[1])
        self.cycle(monitor,payload(False))
        self.assertEqual(self.send.call_count,2)
        self.assertIn('resumed',self.send.call_args.args[1])
        self.assertEqual(monitor.fails,0)

    def test_five_consecutive_failures_abort_round_and_preserve_history(self):
        app.LOCATIONS=['10001','10002','10003','10004','10005','10006']
        monitor=app.Monitor();monitor.seen={('ABCDELL/A','Example Store'):0}
        with patch.object(monitor,'discover',return_value=['ABCDELL/A']),patch.object(app,'get_with_retry',side_effect=ValueError('failed')) as get:
            self.assertFalse(monitor.cycle())
        self.assertEqual(get.call_count,5)
        self.assertEqual(list(monitor.seen.values()),[0])

    def test_grace_counts_only_when_at_least_75_percent_succeeded(self):
        app.LOCATIONS=['10001','10002','10003'];app.STORE_IDS=['R001']
        monitor=app.Monitor();monitor.seen={('ABCDELL/A','Example Store'):0}
        with patch.object(monitor,'discover',return_value=['ABCDELL/A']),patch.object(app,'get_with_retry',side_effect=[payload(False),payload(False),ValueError('fail'),ValueError('fail')]):
            self.assertTrue(monitor.cycle())
        self.assertEqual(list(monitor.seen.values()),[0])
        with patch.object(monitor,'discover',return_value=['ABCDELL/A']),patch.object(app,'get_with_retry',side_effect=[payload(False),payload(False),payload(False),ValueError('fail')]):
            monitor.cycle()
        self.assertEqual(list(monitor.seen.values()),[1])

    def test_pending_notifications_keep_original_two_hour_queue(self):
        monitor=app.Monitor()
        self.send.return_value=False
        monitor.notify('stock','Available')
        self.assertEqual(len(monitor.pending),1)
        self.send.return_value=True
        monitor.flush_pending()
        self.assertEqual(monitor.pending,[])
        self.assertIn('delayed',self.send.call_args.args[1])
        monitor.pending=[('expired','Old',app.time.time()-app.PENDING_MAX_AGE-1)]
        self.send.reset_mock();monitor.flush_pending();self.send.assert_not_called()

    def test_discovery_keeps_original_cache_and_known_part_fallback(self):
        monitor=app.Monitor()
        with patch.object(app,'get_with_retry',return_value='ABCDELL/A OTHERLL/A') as get:
            self.assertEqual(monitor.discover(),['ABCDELL/A'])
            monitor.discover();self.assertEqual(get.call_count,1)
        monitor.parts_time=0
        with patch.object(app,'get_with_retry',side_effect=OSError('offline')):
            self.assertEqual(monitor.discover(),['ABCDELL/A'])

    def test_daily_heartbeat_once_per_day(self):
        app.HEARTBEAT_HOUR=0
        monitor=app.Monitor();monitor.ok_cycles=4
        monitor.heartbeat();monitor.heartbeat()
        self.assertEqual(self.send.call_count,1)
        self.assertIn('4 successful checks',self.send.call_args.args[0])
        app.HEARTBEAT_HOUR=None;monitor.heartbeat_day=None;monitor.heartbeat()
        self.assertEqual(self.send.call_count,1)


class TransportAndSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'config.json'
        self.conf=config()
        cfg._engine=app
        cfg.apply_profile(app,cfg.apply_configuration(app,self.conf)[0])
        patch.object(app.time,'sleep').start()
        patch.object(app,'log').start()
        patch('sys.stdout',new=io.StringIO()).start()
        self.addCleanup(patch.stopall)

    def test_ntfy_uses_original_topic_post_body_headers_and_auth(self):
        app.NTFY_TOPIC='my-existing-topic';app.NTFY_SERVER='https://ntfy.sh';app.NTFY_TOKEN='secret'
        with patch.object(app,'http_text',return_value='{}') as send:
            self.assertTrue(app.send_ntfy('Example München','Monitor started',priority='default',tags='white_check_mark'))
        self.assertEqual(send.call_args.args[0],'https://ntfy.sh/my-existing-topic')
        self.assertEqual(send.call_args.kwargs['data'],'Example München'.encode())
        self.assertEqual(send.call_args.kwargs['headers']['Title'],'Monitor started')
        self.assertEqual(send.call_args.kwargs['headers']['Priority'],'default')
        self.assertEqual(send.call_args.kwargs['headers']['Authorization'],'Bearer secret')
        self.assertEqual(send.call_args.kwargs['timeout'],10)
        self.assertNotIn('Content-Type',send.call_args.kwargs['headers'])

    def test_ntfy_attempts_three_times_then_logs_failure(self):
        app.NTFY_TOPIC='existing'
        with patch.object(app,'http_text',side_effect=OSError('offline')) as send:
            self.assertFalse(app.send_ntfy('text','Title'))
        self.assertEqual(send.call_count,3)

    def test_apple_transient_errors_retry_twice_but_404_does_not(self):
        for status in (429,500,502,503,504,541):
            error=urllib.error.HTTPError('https://www.apple.com',status,'failure',{},None)
            with self.subTest(status=status),patch.object(app,'http_text',side_effect=[error,'ok']) as get:
                self.assertEqual(app.get_with_retry('https://www.apple.com'),'ok')
                self.assertEqual(get.call_count,2)
            error.close()
        error=urllib.error.HTTPError('https://www.apple.com',404,'missing',{},None)
        with patch.object(app,'http_text',side_effect=error) as get,self.assertRaises(urllib.error.HTTPError):
            app.get_with_retry('https://www.apple.com')
        self.assertEqual(get.call_count,1)
        error.close()

    def test_setup_keeps_existing_topic_and_locations_without_posting(self):
        catalog='<a href="/shop/buy-iphone/iphone-example">Buy</a>'
        product='<script type="application/json">'+json.dumps({'data':{'products':[{'category':'iphone','partNumber':'ABCDELL/A','name':'iPhone Example 512GB'}]}})+'</script>'
        row={'storeNumber':'R001','storeName':'Example Store','address':{'postalCode':'10002'},'retailStore':{'timezone':'America/New_York'}}
        answers=['us','10001','all','all','all','','','','','https://ntfy.sh/existing','my-existing-topic']
        with patch('builtins.input',side_effect=answers),patch.object(app,'get_with_retry',side_effect=[catalog,product]) as get,patch.object(cfg,'pickup',return_value=[row]),patch.dict(app.os.environ,{'NTFY_TOKEN':'not-saved'}):
            cfg.setup(self.path)
        saved=cfg.read_json(self.path)
        self.assertEqual(saved['ntfy']['topic'],'my-existing-topic')
        self.assertEqual(saved['locations'],['10001','10002'])
        self.assertEqual(saved['timezone'],'America/New_York')
        self.assertNotIn('not-saved',self.path.read_text())
        self.assertEqual(get.call_count,2)

    def test_old_configuration_restores_missing_location_once(self):
        del self.conf['locations'];cfg.atomic_json(self.path,self.conf)
        with patch.object(app.sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value='10001,10002'):
            result=cfg.load_configuration(self.path,app)
        self.assertEqual(result['locations'],['10001','10002'])
        self.assertEqual(cfg.read_json(self.path)['ntfy'],self.conf['ntfy'])

    def test_background_configuration_without_location_fails_visibly(self):
        del self.conf['locations'];cfg.atomic_json(self.path,self.conf)
        with patch.object(app.sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(cfg.MonitorError,'postal-code searches'):
            cfg.load_configuration(self.path,app)

    def test_main_sends_original_startup_before_inventory_and_survives_error(self):
        self.conf['ntfy']={'enabled':True,'server':'https://ntfy.sh','topic':'existing'}
        cfg.atomic_json(self.path,self.conf)
        with patch.object(app.sys,'argv',['monitor','--config',str(self.path)]),patch.object(app,'Monitor') as cls,patch.object(app.time,'time',side_effect=[0,30,120]),patch.object(app,'send_ntfy'),self.assertRaises(KeyboardInterrupt):
            cls.return_value.cycle.side_effect=[RuntimeError('unexpected'),KeyboardInterrupt()]
            app.main()
        self.assertIn('Monitoring started',cls.return_value.notify.call_args.args[0])
        self.assertEqual(cls.return_value.notify.call_args.kwargs['priority'],'default')
        cls.return_value.register_failure.assert_called_once()

    def test_real_main_startup_constructs_a_post_to_the_configured_topic(self):
        self.conf['ntfy']={'enabled':True,'server':'https://ntfy.sh','topic':'my-existing-topic'}
        cfg.atomic_json(self.path,self.conf)
        response=unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value=b'{"id":"mock-accepted-message"}'
        with patch.object(app.sys,'argv',['monitor','--config',str(self.path)]),patch.object(app.urllib.request,'urlopen',return_value=response) as send,patch.object(app,'network_ok',return_value=False),patch.object(app.time,'sleep',side_effect=KeyboardInterrupt()),self.assertRaises(KeyboardInterrupt):
            app.main()
        request=send.call_args.args[0]
        self.assertEqual(request.get_method(),'POST')
        self.assertEqual(request.full_url,'https://ntfy.sh/my-existing-topic')
        self.assertIn(b'Monitoring started',request.data)
        self.assertEqual(request.get_header('Title'),'iPhone monitor active')
        self.assertEqual(send.call_args.kwargs['timeout'],10)

    def test_once_skips_startup(self):
        self.conf['ntfy']={'enabled':True,'server':'https://ntfy.sh','topic':'existing'};cfg.atomic_json(self.path,self.conf)
        with patch.object(app.sys,'argv',['monitor','--once','--config',str(self.path)]),patch.object(app,'Monitor') as cls,self.assertRaises(SystemExit) as caught:
            cls.return_value.cycle.return_value=True
            app.main()
        self.assertEqual(caught.exception.code,0)
        cls.return_value.notify.assert_not_called()

    def test_multiple_families_have_separate_original_monitors(self):
        self.conf['products'].append({'part':'OTHERLL/A','name':'iPhone Other','url':'https://www.apple.com/shop/buy-iphone/iphone-other'})
        profiles=cfg.apply_configuration(app,self.conf)
        self.assertEqual(len(profiles),2)
        cfg.apply_profile(app,profiles[1])
        self.assertEqual(app.PRODUCT_FILTER,'other')
        self.assertEqual(app.EXTRA_PARTS,['OTHERLL/A'])

    def test_model_choice_supplies_the_original_name_filter_for_pro_max(self):
        self.conf['products']=[{'part':'ABCDELL/A','name':'iPhone 18 Pro Max 512GB Black',
                               'url':'https://www.apple.com/shop/buy-iphone/iphone-18-pro'}]
        profile=cfg.apply_configuration(app,self.conf)[0]
        cfg.apply_profile(app,profile)
        self.assertEqual(app.PRODUCT_FILTER,'18 pro max')

    def test_urls_and_configuration_validation(self):
        self.assertEqual(cfg.shop_url('it'),'https://www.apple.com/it/shop/')
        self.assertEqual(cfg.shop_url('cn'),'https://www.apple.com.cn/shop/')
        url='https://www.apple.com/shop/buy-iphone/iphone-example'
        self.assertEqual(cfg.product_url(f'[Apple]({url})',self.conf['shop_url']),url)
        for value in ('http://www.apple.com/shop/','https://www.apple.com.evil.test/shop/'):
            with self.assertRaises(cfg.MonitorError):cfg.shop_url(value)
        for interval in (0,True,float('nan')):
            invalid=copy.deepcopy(self.conf);invalid['interval_minutes']=interval
            with self.assertRaises(cfg.MonitorError):cfg.validate(invalid)

    def test_tls_remains_verified_and_respects_explicit_ca_settings(self):
        with patch.object(app.sys,'platform','darwin'),patch.dict(app.os.environ,{},clear=True),patch.object(app.Path,'is_file',return_value=True),patch.object(app.ssl,'create_default_context') as create:
            app.tls_context()
            create.assert_called_once_with()
            create.return_value.load_verify_locations.assert_called_once_with(cafile='/etc/ssl/cert.pem')
        with patch.object(app.sys,'platform','darwin'),patch.dict(app.os.environ,{'SSL_CERT_FILE':'/custom/trust'},clear=True),patch.object(app.ssl,'create_default_context') as create:
            app.tls_context();create.return_value.load_verify_locations.assert_not_called()


if __name__=='__main__':unittest.main()
