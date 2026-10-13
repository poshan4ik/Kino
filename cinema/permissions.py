from rest_framework import permissions


class IsAdminOrManager(permissions.BasePermission):
    """Доступ для администраторов и менеджеров"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['admin', 'manager']


class IsCashierOrAbove(permissions.BasePermission):
    """Доступ для кассиров, контролёров, менеджеров и админов"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['cashier', 'controller', 'manager', 'admin']


class IsCashierRole(permissions.BasePermission):
    """Кассир/менеджер/админ — операции продажи, отмены и возврата (без контролёра)"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['cashier', 'manager', 'admin']


class IsControllerOrAbove(permissions.BasePermission):
    """Доступ для контролёров, менеджеров и админов"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['controller', 'manager', 'admin']


class IsOwnerOrStaff(permissions.BasePermission):
    """Владелец объекта или персонал (кассир+)"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if request.user.role in ['cashier', 'controller', 'manager', 'admin']:
            return True
        return obj.client == request.user


class PublicReadOnly(permissions.BasePermission):
    """Публичный доступ на чтение, запись только для авторизованных"""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated