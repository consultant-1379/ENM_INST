from mock import patch, MagicMock
from unittest2 import TestCase
from crypto_service import CryptoService, create_parser
import requests


class TestCryptoService(TestCase):

    def setUp(self):
        self.crypto_service = CryptoService(verbose=True)

    @patch('requests.post')
    def test_crypto_service(self, rp):
        response = MagicMock()
        response.status_code = 200
        rp.return_value = response

        result = self.crypto_service.crypto_service_update()
        self.assertEquals(result, 200)
        self.assertTrue(rp.called)

    @patch('requests.post')
    @patch('logging.Logger.warn')
    def negative_test_crypto_service(self, logger, rp):
        response = MagicMock()
        response.status_code = 500
        rp.return_value = response
        result = self.crypto_service.crypto_service_update()
        self.assertEquals(result, 500)
        self.assertTrue(rp.called)
        logger.assert_called_with("Cryptoservice Hardening is failed. Http code 500")

    @patch('requests.post')
    @patch('logging.Logger.warn')
    def server_unavailable_test_crypto_service(self, logger, rp):
        rp.side_effect = requests.exceptions.RequestException('Server unavailable')
        result = self.crypto_service.crypto_service_update()
        self.assertTrue(rp.called)
        self.assertEquals(result, 0)
        logger.assert_called_with("Cryptoservice Hardening is failed. Exception Server unavailable")

    def test_create_parser(self):
        parser = create_parser()
        self.assertTrue(parser)
