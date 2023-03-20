from http import HTTPStatus

from django.test import TestCase


class ViewErrorTests(TestCase):
    def test_inaccessible_page(self):
        """Несуществующая cтраница '/test/' недоступна"""
        response = self.client.get('/test/')
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, 'core/404.html')
