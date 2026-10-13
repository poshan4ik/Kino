"""Единый формат ошибок API: {'error': <русское сообщение>, 'code': <HTTP-код>}."""
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.views import exception_handler

RU_MESSAGES = {
    status.HTTP_401_UNAUTHORIZED: _('Требуется аутентификация'),
    status.HTTP_403_FORBIDDEN: _('Доступ запрещён'),
    status.HTTP_404_NOT_FOUND: _('Объект не найден'),
}


def _flatten(detail):
    """Сводит detail/словарь полей DRF к одной строке."""
    if isinstance(detail, dict):
        parts = []
        for field, errors in detail.items():
            if isinstance(errors, (list, tuple)):
                errors = ', '.join(str(e) for e in errors)
            parts.append(f'{field}: {errors}' if field != 'detail' else str(errors))
        return '; '.join(parts)
    if isinstance(detail, (list, tuple)):
        return '; '.join(str(e) for e in detail)
    return str(detail)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = getattr(exc, 'detail', None)
    message = _flatten(detail) if detail is not None else RU_MESSAGES.get(
        response.status_code, _('Произошла ошибка')
    )
    # Стандартные англоязычные сообщения DRF заменяем русскими
    default_details = {
        'Authentication credentials were not provided.',
        'Invalid token.',
        'User is not active.',
        'You do not have permission to perform this action.',
        'Not found.',
        'Invalid pk "..." - object does not exist.',
    }
    if str(detail) in default_details or str(detail).startswith('Invalid pk'):
        message = RU_MESSAGES.get(response.status_code, message)

    response.data = {'error': message, 'code': response.status_code}
    return response
