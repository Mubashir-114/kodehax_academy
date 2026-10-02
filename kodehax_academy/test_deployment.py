from unittest.mock import patch

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.middleware.security import SecurityMiddleware

from adminpanel.middleware import MaintenanceModeMiddleware


class DeploymentHealthTests(SimpleTestCase):
    def test_health_bypasses_maintenance_database_lookup(self):
        middleware = MaintenanceModeMiddleware(lambda request: JsonResponse({"status": "healthy"}))
        with patch("adminpanel.middleware.SiteSettings.load") as load:
            response = middleware(RequestFactory().get("/health/"))
        self.assertEqual(response.status_code, 200)
        load.assert_not_called()

    @override_settings(SECURE_SSL_REDIRECT=True,
                       SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
                       SECURE_REDIRECT_EXEMPT=[r"^health/$"])
    def test_render_proxy_https_and_plain_http_health(self):
        middleware = SecurityMiddleware(lambda request: JsonResponse({"ok": True}))
        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="https")
        self.assertTrue(request.is_secure())
        self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware(RequestFactory().get("/health/")).status_code, 200)


class DatabaseTLSTests(SimpleTestCase):
    def test_tls_rejects_server_without_encryption_before_authentication(self):
        import ssl
        import pymysql
        from kodehax_academy import VerifiedTLSConnection

        connection = VerifiedTLSConnection(defer_connect=True, ssl=ssl.create_default_context())
        connection.server_capabilities = 0
        with self.assertRaises(pymysql.OperationalError):
            connection._request_authentication()
        self.assertEqual(connection.ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(connection.ctx.check_hostname)
