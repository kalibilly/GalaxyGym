from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import hashlib
import json


class CacheKey:
    """Consistent cache key generation."""
    
    @staticmethod
    def dashboard_metrics():
        return 'dashboard:metrics'
    
    @staticmethod
    def task_statistics(hours=24):
        return f'task:statistics:{hours}h'
    
    @staticmethod
    def member_list(page=1, filters=None):
        if filters is None:
            filters = {}
        filters_str = json.dumps(filters, sort_keys=True, default=str)
        filters_hash = hashlib.md5(filters_str.encode()).hexdigest()
        return f'members:list:p{page}:{filters_hash}'
    
    @staticmethod
    def invoice_list(page=1, filters=None):
        if filters is None:
            filters = {}
        filters_str = json.dumps(filters, sort_keys=True, default=str)
        filters_hash = hashlib.md5(filters_str.encode()).hexdigest()
        return f'invoices:list:p{page}:{filters_hash}'
    
    @staticmethod
    def attendance_list(page=1, filters=None):
        if filters is None:
            filters = {}
        filters_str = json.dumps(filters, sort_keys=True, default=str)
        filters_hash = hashlib.md5(filters_str.encode()).hexdigest()
        return f'attendance:list:p{page}:{filters_hash}'


def cache_dashboard_metrics(ttl=300):
    """Cache dashboard metrics with fallback to fresh computation."""
    key = CacheKey.dashboard_metrics()
    cached = cache.get(key)
    if cached:
        return cached
    
    from core.services import get_dashboard_metrics
    metrics = get_dashboard_metrics()
    cache.set(key, metrics, ttl)
    return metrics


def invalidate_dashboard_cache():
    """Invalidate dashboard cache after relevant writes."""
    cache.delete(CacheKey.dashboard_metrics())


def invalidate_task_cache():
    """Invalidate task statistics cache."""
    for hours in [24, 168]:
        cache.delete(CacheKey.task_statistics(hours))


def cache_get_or_compute(key, compute_fn, ttl=300):
    """Generic cache helper: try cache, fall back to computation."""
    cached = cache.get(key)
    if cached is not None:
        return cached
    
    result = compute_fn()
    cache.set(key, result, ttl)
    return result


def paginate_queryset(queryset, page, page_size=15):
    """
    Paginate a queryset safely.
    
    Returns: (page_obj, paginator, is_paginated)
    """
    paginator = Paginator(queryset, page_size)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    return page_obj, paginator, paginator.num_pages > 1


def get_paginated_context(page_obj, paginator):
    """Build context dict for paginated template rendering."""
    return {
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': paginator.num_pages > 1,
        'page_number': page_obj.number,
        'total_pages': paginator.num_pages,
        'total_items': paginator.count,
        'start_index': page_obj.start_index(),
        'end_index': page_obj.end_index(),
    }
