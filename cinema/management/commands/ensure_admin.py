"""Автосоздание суперпользователя при деплое (пароль только из окружения)."""
import os

from django.core.management.base import BaseCommand, CommandError

from cinema.models import User


class Command(BaseCommand):
    help = (
        'Создаёт суперпользователя из переменных окружения '
        'ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD. '
        'Без ADMIN_PASSWORD команда ничего не делает (безопасно).'
    )

    def handle(self, *args, **options):
        username = os.getenv('ADMIN_USERNAME', '').strip()
        email = os.getenv('ADMIN_EMAIL', '').strip()
        password = os.getenv('ADMIN_PASSWORD', '')

        if not username or not password:
            self.stdout.write(
                'ADMIN_USERNAME/ADMIN_PASSWORD не заданы — пропускаю создание '
                'суперпользователя.'
            )
            return

        user = User.objects.filter(username=username).first()
        if user:
            changed = False
            if not user.is_superuser:
                user.is_superuser = True
                user.is_staff = True
                user.role = 'admin'
                changed = True
            if password and not user.check_password(password):
                user.set_password(password)
                changed = True
            if changed:
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Суперпользователь {username} обновлён.'
                ))
            else:
                self.stdout.write(f'Суперпользователь {username} уже настроен.')
            return

        User.objects.create_superuser(
            username=username,
            email=email or f'{username}@localhost',
            password=password,
            role='admin',
        )
        self.stdout.write(self.style.SUCCESS(
            f'Суперпользователь {username} создан.'
        ))
