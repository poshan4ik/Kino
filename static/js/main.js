// АИС «Аврора» - Основной JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация тултипов
    initTooltips();
    
    // Инициализация выпадающих меню
    initDropdowns();
    
    // Обработка формы бронирования
    initBookingForm();
    
    // Обработка схемы зала
    initHallSchema();
    
    // Автообновление таймеров
    initTimers();
    
    // Плавная прокрутка
    initSmoothScroll();
});

// Тултипы Bootstrap
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Выпадающие меню
function initDropdowns() {
    const dropdownElementList = [].slice.call(document.querySelectorAll('.dropdown-toggle'));
    dropdownElementList.map(function(dropdownToggleEl) {
        return new bootstrap.Dropdown(dropdownToggleEl);
    });
}

// Форма бронирования
function initBookingForm() {
    const bookingForms = document.querySelectorAll('.booking-form');
    bookingForms.forEach(form => {
        form.addEventListener('submit', handleBookingSubmit);
    });
    
    // Выбор сеанса
    const sessionPills = document.querySelectorAll('.session-pill-btn');
    sessionPills.forEach(pill => {
        pill.addEventListener('click', function() {
            if (!this.disabled) {
                sessionPills.forEach(p => p.classList.remove('selected'));
                this.classList.add('selected');
                const input = document.querySelector('#id_session');
                if (input) input.value = this.dataset.sessionId;
            }
        });
    });
}

async function handleBookingSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="loading-spinner me-2"></span>Обработка...';
    
    try {
        const formData = new FormData(form);
        const response = await fetch('/api/bookings/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('Бронирование создано! Ожидает оплаты.', 'success');
            setTimeout(() => window.location.href = '/profile/', 1500);
        } else {
            showToast(data.detail || 'Ошибка при бронировании', 'danger');
        }
    } catch (error) {
        showToast('Ошибка сети', 'danger');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// Схема зала
function initHallSchema() {
    const seats = document.querySelectorAll('.seat:not(.booked)');
    const selectedSeats = new Set();
    const maxSeats = 8;
    
    seats.forEach(seat => {
        seat.addEventListener('click', function() {
            const seatId = this.dataset.seatId;
            
            if (this.classList.contains('selected')) {
                this.classList.remove('selected');
                selectedSeats.delete(seatId);
            } else {
                if (selectedSeats.size >= maxSeats) {
                    showToast(`Максимум ${maxSeats} мест за раз`, 'warning');
                    return;
                }
                this.classList.add('selected');
                selectedSeats.add(seatId);
            }
            
            updateSeatSelection(selectedSeats);
        });
    });
}

function updateSeatSelection(selectedSeats) {
    const hiddenInput = document.querySelector('#id_seats');
    if (hiddenInput) {
        hiddenInput.value = Array.from(selectedSeats).join(',');
    }
    
    const countEl = document.querySelector('#selected-count');
    const totalEl = document.querySelector('#total-price');
    if (countEl) countEl.textContent = selectedSeats.size;
    
    // Пересчет цены
    let total = 0;
    selectedSeats.forEach(seatId => {
        const seat = document.querySelector(`.seat[data-seat-id="${seatId}"]`);
        if (seat) {
            total += parseFloat(seat.dataset.price || 0);
        }
    });
    if (totalEl) totalEl.textContent = total.toFixed(2);
}

// Таймеры для бронирований
function initTimers() {
    const timers = document.querySelectorAll('[data-expires-at]');
    
    function updateTimers() {
        const now = new Date();
        timers.forEach(el => {
            const expiresAt = new Date(el.dataset.expiresAt);
            const diff = expiresAt - now;
            
            if (diff <= 0) {
                el.textContent = 'Просрочено';
                el.classList.add('text-danger');
                el.classList.remove('text-warning', 'text-success');
            } else {
                const minutes = Math.floor(diff / 60000);
                const seconds = Math.floor((diff % 60000) / 1000);
                el.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                
                if (minutes < 5) {
                    el.classList.add('text-danger');
                    el.classList.remove('text-warning', 'text-success');
                } else if (minutes < 10) {
                    el.classList.add('text-warning');
                    el.classList.remove('text-danger', 'text-success');
                } else {
                    el.classList.add('text-success');
                    el.classList.remove('text-danger', 'text-warning');
                }
            }
        });
    }
    
    if (timers.length > 0) {
        updateTimers();
        setInterval(updateTimers, 1000);
    }
}

// Плавная прокрутка
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
}

// Уведомления (Toast)
function showToast(message, type = 'info') {
    const container = getOrCreateToastContainer();
    
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type} border-0 session-pill`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

function getOrCreateToastContainer() {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '1080';
        document.body.appendChild(container);
    }
    return container;
}

// Получение CSRF токена
function getCSRFToken() {
    const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
}

// Форматирование цены
function formatPrice(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount);
}

// Форматирование даты
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('ru-RU', {
        day: 'numeric',
        month: 'long',
        weekday: 'short'
    }).format(date);
}

// Форматирование времени
function formatTime(timeString) {
    return timeString.slice(0, 5);
}

// Дебаунс
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// API хелперы
const API = {
    async get(endpoint) {
        const response = await fetch(`/api${endpoint}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        return response.json();
    },
    
    async post(endpoint, data) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async patch(endpoint, data) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async delete(endpoint) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        return response.ok;
    }
};

// Экспорт для модулей
window.AuroraCinema = {
    API,
    showToast,
    formatPrice,
    formatDate,
    formatTime,
    debounce
};