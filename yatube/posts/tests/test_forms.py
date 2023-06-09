import tempfile
import shutil

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from ..models import Group, Post, Comment, Follow


User = get_user_model()

TEMP_MEDIA_ROOT = tempfile.mkdtemp(dir=settings.BASE_DIR)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PostFormTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = User.objects.create_user(username='auth')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test-slug',
        )
        cls.post = Post.objects.create(
            author=cls.user,
            text='Тестовый пост',
            group=cls.group,
        )
        cls.small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x02\x00'
            b'\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xFF\xFF\xFF\x21\xF9\x04\x00\x00'
            b'\x00\x00\x00\x2C\x00\x00\x00\x00'
            b'\x02\x00\x01\x00\x00\x02\x02\x0C'
            b'\x0A\x00\x3B'
        )

    def setUp(self):
        self.auth_client = Client()
        self.auth_client.force_login(self.user)

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def test_create_post(self):
        """Валидная форма создает запись в Post."""
        uploaded = SimpleUploadedFile(
            name='small.gif',
            content=self.small_gif,
            content_type='image/gif'
        )
        post_text = 'Тестовый текст'
        form_data = {
            'text': post_text,
            'group': self.group.id,
            'image': uploaded
        }
        posts_count = Post.objects.count()
        # Отправляем POST-запрос
        response = self.auth_client.post(
            reverse('posts:post_create'),
            data=form_data,
            follow=True
        )

        # Проверяем, увеличилось ли число постов
        self.assertEqual(Post.objects.count(), posts_count + 1)

        # Проверяем, сработал ли редирект
        self.assertRedirects(response, reverse(
            'posts:profile',
            kwargs={'username': self.user.username})
        )

        # Проверяем, что создалась запись с заданным слагом
        self.assertTrue(
            Post.objects.filter(
                group=self.group,
                text=post_text,
                image='posts/small.gif',
            ).exists()
        )

    def test_edit_post(self):
        """Валидная форма редактирует запись в Post."""
        new_group = Group.objects.create(
            title='Новая тестовая группа',
            slug='new-test-slug',
        )

        uploaded = SimpleUploadedFile(
            name='small.gif',
            content=self.small_gif,
            content_type='image/gif'
        )

        new_text_post = 'Измененный тестовый текст'
        form_data = {
            'text': new_text_post,
            'group': new_group.id,
            'image': uploaded,
        }

        posts_count = Post.objects.count()
        # Отправляем POST-запрос
        response = self.auth_client.post(
            reverse('posts:post_edit', kwargs={'post_id': self.post.id}),
            data=form_data,
            follow=True
        )

        # Проверяем, осталось ли количество постов неизменным
        self.assertEqual(Post.objects.count(), posts_count)

        # Проверяем, сработал ли редирект
        self.assertRedirects(response, reverse(
            'post:post_detail',
            kwargs={'post_id': self.post.id})
        )

        # Проверяем, что запись изменилась
        new_post = Post.objects.get(id=self.post.id)
        self.assertEqual(new_post.text, new_text_post)
        self.assertEqual(new_post.group, new_group)
        self.assertEqual(new_post.image.name, f"posts/{uploaded.name}")

    def test_error_in_form_sent_not_picture(self):
        """Проверка, ошибки при отправки не картинки."""
        uploaded = SimpleUploadedFile(
            name='file.txt',
            content=b'file_content',
        )
        form_data = {
            'text': self.post.text,
            'image': uploaded,
        }
        # Изменяем POST-запрос с некорректным файлом
        response = self.auth_client.post(
            reverse('posts:post_edit', kwargs={'post_id': self.post.id}),
            data=form_data,
            follow=True
        )

        # Проверяем, что форма возвращает ошибку
        self.assertFormError(
            response,
            'form',
            'image',
            ('Загрузите правильное изображение. Файл, который вы загрузили, '
             'поврежден или не является изображением.')
        )

    def test_comment_post_auth_user(self):
        """Валидная форма создает Comment."""
        comments_count = Comment.objects.count()
        comment_text = 'Тестовый комментарий'
        form_data = {
            'text': comment_text,
            'post': self.post,
            'author': self.user,
        }
        # Отправляем POST-запрос
        response = self.auth_client.post(
            reverse('posts:add_comment',
                    kwargs={'post_id': self.post.id}),
            data=form_data,
            follow=True
        )

        # Проверяем, увеличилось ли число комментариев
        self.assertEqual(Comment.objects.count(), comments_count + 1)

        # Проверяем, сработал ли редирект
        self.assertRedirects(response, reverse(
            'posts:post_detail',
            kwargs={'post_id': self.post.id})
        )

        # Проверяем, что создался пост для поста
        self.assertTrue(
            Comment.objects.filter(
                post=self.post,
                text=comment_text,
                author=self.user,
            ).exists()
        )

    def test_comment_post_guest_user(self):
        """Валидная форма не создает Comment для любого пользователя."""
        guest_client = Client()
        comment_text = 'Тестовый комментарий'
        form_data = {
            'text': comment_text,
            'post': self.post,
            'author': self.user,
        }
        # Отправляем POST-запрос
        guest_client.post(
            reverse('posts:add_comment',
                    kwargs={'post_id': self.post.id}),
            data=form_data,
            follow=True
        )

        # Проверяем, что не создался комментарий для поста
        self.assertFalse(
            Comment.objects.filter(
                post=self.post,
                text=comment_text,
                author=self.user,
            ).exists()
        )

    def test_follow(self):
        """Проверка подписки на автора"""
        new_user = User.objects.create_user(username='new_user')

        # Проверяем, что пользователь подписался
        self.auth_client.get(reverse(
            'posts:profile_follow',
            kwargs={'username': new_user.username})
        )
        self.assertTrue(
            Follow.objects.filter(
                user=self.user,
                author=new_user,
            ).exists()
        )

    def test_unfollow(self):
        """Проверка отписки на автора"""
        new_user = User.objects.create_user(username='new_user')
        Follow.objects.create(user=new_user, author=self.user)

        # Проверяем, что пользователь отписался
        self.auth_client.get(reverse(
            'posts:profile_unfollow',
            kwargs={'username': new_user.username})
        )
        self.assertFalse(
            Follow.objects.filter(
                user=self.user,
                author=new_user,
            ).exists()
        )
