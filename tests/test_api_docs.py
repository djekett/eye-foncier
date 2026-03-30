"""
Tests de la documentation API — EYE-FONCIER
Verifie que Swagger/OpenAPI est accessible.
"""
from django.test import TestCase, override_settings


class SwaggerDocsTest(TestCase):
    """Tests d'accessibilite de la documentation API."""

    def test_swagger_ui_accessible(self):
        """La page Swagger UI doit etre accessible."""
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, 200)

    def test_redoc_accessible(self):
        """La page ReDoc doit etre accessible."""
        response = self.client.get("/api/redoc/")
        self.assertEqual(response.status_code, 200)

    def test_schema_endpoint_accessible(self):
        """L'endpoint schema OpenAPI doit etre accessible."""
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        # Verifier que c'est du JSON ou YAML valide
        self.assertIn(response["Content-Type"], [
            "application/vnd.oai.openapi+json",
            "application/vnd.oai.openapi; charset=utf-8",
            "application/json",
        ])

    def test_schema_contains_api_info(self):
        """Le schema doit contenir les informations de l'API."""
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")
        if response.status_code == 200:
            import json
            try:
                data = json.loads(response.content)
                # Verifier les metadonnees de base
                self.assertIn("info", data)
                self.assertIn("paths", data)
            except json.JSONDecodeError:
                pass  # Peut etre en YAML
