import tempfile
import shutil
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.core.paginator import Page
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.core.cache import cache

from ..models import Group, Post, Follow

User = get_user_model()

TEMP_MEDIA_ROOT = tempfile.mkdtemp(dir=settings.BASE_DIR)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PostPagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x02\x00'
            b'\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xFF\xFF\xFF\x21\xF9\x04\x00\x00'
            b'\x00\x00\x00\x2C\x00\x00\x00\x00'
            b'\x02\x00\x01\x00\x00\x02\x02\x0C'
            b'\x0A\x00\x3B'
        )
        cls.uploaded = SimpleUploadedFile(
            name='small.gif',
            content=small_gif,
            content_type='image/gif'
        )

        user = User.objects.create_user(username='auth-1')
        group = Group.objects.create(
            title='Тестовая группа-1',
            slug='test-slug-1',
        )
        Post.objects.create(
            author=user,
            text='Тестовый пост другого пользователя',
            group=group,
        )
        Post.objects.create(
            author=user,
            text='Тестовый пост другого пользователя без группы',
        )

        cls.user = User.objects.create_user(username='auth')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test-slug',
        )
        cls.post = Post.objects.create(
            author=cls.user,
            text='Тестовый пост',
            group=cls.group,
            image=cls.uploaded
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.auth_client = Client()
        self.auth_client.force_login(self.user)

    def test_pages_correct_template(self):
        "Во view-функциях используются правильные html-шаблоны"

        views = {
            'posts:main_menu': {
                'address': 'posts/index.html',
            },
            'posts:group_posts': {
                'address': 'posts/group_list.html',
                'kwargs': {'slug': self.group.slug}
            },
            'posts:profile': {
                'address': 'posts/profile.html',
                'kwargs': {'username': self.user.username}
            },
            'posts:post_detail': {
                'address': 'posts/post_detail.html',
                'kwargs': {'post_id': self.post.id}
            },
            'posts:post_create': {
                'address': 'posts/create_post.html',
            },
            'posts:post_edit': {
                'address': 'posts/create_post.html',
                'kwargs': {'post_id': self.post.id}
            },
        }
        for view, view_args in views.items():
            with self.subTest(view):
                address = view_args.get('address')
                address_kwargs = view_args.get('kwargs')
                try:
                    if address_kwargs:
                        reverse_view = reverse(view, kwargs=address_kwargs)
                    else:
                        reverse_view = reverse(view)

                except NoReverseMatch as e:
                    assert False, (f'''Не найдены аргументы для view функции
                                       {view}.Ошибка: `{e}`''')
                response = self.auth_client.get(reverse_view)
                self.assertTemplateUsed(response, address)

    def test_page_posts_show_correct_context(self):
        """Шаблон страниц c постами сформированы с правильным контекстом."""

        values = {
            'text': self.post.text,
            'group': self.group,
            'id': self.post.id,
            'author': self.user,
            'image': self.post.image
        }
        views = {
            reverse('posts:main_menu'): values,
            reverse('posts:group_posts',
                    kwargs={'slug': self.group.slug}
                    ): values,
            reverse('posts:profile',
                    kwargs={'username': self.user.username}
                    ): values,
            reverse('posts:post_detail',
                    kwargs={'post_id': self.post.id}
                    ): values,
        }
        for reverse_view, context_values in views.items():
            with self.subTest(reverse_view):
                response = self.auth_client.get(reverse_view)

                if response.context.get('page_obj'):
                    paginator = response.context.get('page_obj')
                    self.assertIsInstance(paginator, Page)
                    post = paginator[0]
                else:
                    post = response.context.get('post')

                self.assertIsInstance(post, Post)
                for key, value in context_values.items():
                    self.assertEqual(getattr(post, key), value)

    def test_page_forms_show_correct_context(self):
        """Шаблон страниц с формами сформированы с правильным контекстом."""
        form_fields = {
            'text': forms.fields.CharField,
            'group': forms.fields.ChoiceField,
            'image': forms.fields.ImageField,
        }
        views = {
            'posts:post_create': None,
            'posts:post_edit': {'post_id': self.post.id},
        }
        for name_view, view_kwargs in views.items():
            response = self.auth_client.get(
                reverse(name_view, kwargs=view_kwargs)
            )
            for value, expected in form_fields.items():
                with self.subTest(value=value):
                    form_field = response.context.get('form').fields.get(value)
                    self.assertIsInstance(form_field, expected)

    def test_follow_index_show_correct_context(self):
        """
        Новая запись пользователя появляется в ленте тех, кто на него
        подписан и не появляется в ленте тех, кто не подписан.
        """
        user_folower = User.objects.create_user(username='folower')
        folower = Client()
        folower.force_login(user_folower)

        user_no_folower = User.objects.create_user(username='no_folower')
        no_folower = Client()
        no_folower.force_login(user_no_folower)

        Follow.objects.create(user=user_folower, author=self.user)

        new_post = Post.objects.create(
            author=self.user,
            text='Тестовый пост для подписчиков',
        )

        # Проверяем, что у подписанного пользователя появилась новая запись
        response = folower.get(reverse('posts:follow_index'))
        new_post_on_page = response.context.get('page_obj')[0]
        self.assertEqual(new_post_on_page, new_post)

        # Проверяем, что у неподписанного пользователя нет новых записей
        response = no_folower.get(reverse('posts:follow_index'))
        self.assertEqual(len(response.context.get('page_obj')), 0)

    def test_cache_main_menu(self):
        """Проверка работы кеша на главной странице"""
        old_response = self.auth_client.get(reverse('posts:main_menu'))
        Post.objects.create(
            author=self.user,
            text='Тестовый пост для проверки работы кэша',
            group=self.group
        )
        response = self.auth_client.get(reverse('posts:main_menu'))
        self.assertEqual(old_response.content, response.content)
        cache.clear()
        new_response = self.auth_client.get(reverse('posts:main_menu'))
        self.assertNotEqual(new_response.content, response.content)


class PaginatorViewsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username='auth')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test-slug',
        )

        post = Post(author=cls.user, text='Тестовый пост', group=cls.group)
        Post.objects.bulk_create([post] * 13)

        cls.views = {
            reverse('posts:main_menu'): 'page_obj',
            reverse('posts:group_posts',
                    kwargs={'slug': cls.group.slug}
                    ): 'page_obj',
            reverse('posts:profile',
                    kwargs={'username': cls.user.username}
                    ): 'page_obj',
        }

    def setUp(self):
        cache.clear()
        self.auth_client = Client()
        self.auth_client.force_login(self.user)

    def test_pagintors(self):
        for reverse_view, key in self.views.items():
            with self.subTest(reverse_view):
                response = self.client.get(reverse_view)
                # Проверка: количество постов на первой странице равно 10.
                self.assertEqual(len(response.context[key]), 10)

                response = self.client.get(reverse_view + '?page=2')
                # Проверка: на второй странице должно быть три поста.
                self.assertEqual(len(response.context[key]), 3)
