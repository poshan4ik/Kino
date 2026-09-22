from rest_framework import permissions


class IsAdminOrManager(permissions.BasePermission):
    """Доступ для администраторов и менеджеров"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['admin', 'manager']


class IsAdmin(permissions.BasePermission):
    """Доступ только для администраторов"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'admin'


class IsCashierOrAbove(permissions.BasePermission):
    """Доступ для кассиров, контролёров, менеджеров и админов"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['cashier', 'controller', 'manager', 'admin']


class IsControllerOrAbove(permissions.BasePermission):
    """Доступ для контролёров, менеджеров и админов"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ['controller', 'manager', 'admin']


class IsOwnerOrStaff(permissions.BasePermission):
    """Владелец объекта или персонал (кассир+)"""
    
    def has_object_permission(self, request, view, obj):
        if request.user.role in ['cashier', 'controller', 'manager', 'admin']:
            return True
        return obj.client == request.user


class IsClientOrReadOnly(permissions.BasePermission):
    """Клиенты могут видеть только свои данные, персонал — всё"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if request.user.role in ['cashier', 'controller', 'manager', 'admin']:
            return True
        if hasattr(obj, 'client'):
            return obj.client == request.user
        if hasattr(obj, 'booking'):
            return obj.booking.client == request.user
        return False


class ReadOnly(permissions.BasePermission):
    """Только чтение для всех авторизованных"""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.method in permissions.SAFE_METHODS


class PublicReadOnly(permissions.BasePermission):
    """Публичный доступ на чтение, запись только для авторизованных"""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated