// Безопасный вывод текста в HTML. На странице настроек функция уже есть (settings.js),
// на отдельных страницах групп/тарифов/вознаграждений — объявляем здесь.
if (typeof window.escapeHtml !== 'function') {
    window.escapeHtml = (value) => String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const tariffEditIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const tariffTrashIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>';

// Загрузка тарифов
async function loadTariffs() {
    try {
        const response = await fetch('/api/tariffs');
        const tariffs = await response.json();
        
        const tbody = document.getElementById('tariffsTableBody');
        
        if (tariffs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #95a5a6;">Нет тарифов</td></tr>';
            return;
        }
        
        tbody.innerHTML = tariffs.map(t => `
            <tr>
                <td><strong>${escapeHtml(t.name)}</strong></td>
                <td>${t.lessons_count}</td>
                <td>${t.price.toLocaleString('ru-RU')} сум</td>
                <td>${t.price_per_lesson.toLocaleString('ru-RU')} сум</td>
                <td>${t.description ? escapeHtml(t.description) : '-'}</td>
                <td class="action-buttons">
                    <button class="btn-small btn-info edit-tariff-btn" data-tariff-id="${t.id}" title="Изменить">${tariffEditIcon}</button>
                    <button class="btn-small btn-danger delete-tariff-btn" data-tariff-id="${t.id}" data-tariff-name="${escapeHtml(t.name)}" title="Удалить">${tariffTrashIcon}</button>
                </td>
            </tr>
        `).join('');
        
        // Обработчики кнопок
        attachTariffButtons();
    } catch (error) {
        console.error('Ошибка загрузки тарифов:', error);
    }
}

// Модальные окна - инициализация только если элементы существуют
(function initTariffModals() {
    const addTariffModal = document.getElementById('addTariffModal');
    const editTariffModal = document.getElementById('editTariffModal');
    const addTariffBtn = document.getElementById('addTariffBtnHeader') || document.getElementById('addTariffBtn');
    
    if (!addTariffBtn || !addTariffModal || !editTariffModal) {
        return; // Элементы не найдены
    }
    
    // Открыть модалку добавления
    addTariffBtn.addEventListener('click', () => {
        addTariffModal.style.display = 'block';
    });
    
    // Закрыть модалки через кнопки закрытия
    const closeBtns = document.querySelectorAll('#addTariffModal .close, #editTariffModal .close');
    closeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            addTariffModal.style.display = 'none';
            editTariffModal.style.display = 'none';
        });
    });
    
    // Закрыть при клике вне модалки
    window.addEventListener('click', (e) => {
        if (e.target === addTariffModal) addTariffModal.style.display = 'none';
        if (e.target === editTariffModal) editTariffModal.style.display = 'none';
    });
})();

// Добавить тариф
document.getElementById('addTariffForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const data = {
        name: formData.get('name'),
        lessons_count: formData.get('lessons_count'),
        price: formData.get('price'),
        description: formData.get('description')
    };
    
    try {
        const response = await fetch('/api/tariffs/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert('✓ Тариф успешно добавлен!');
            addTariffModal.style.display = 'none';
            e.target.reset();
            loadTariffs();
        } else {
            alert('Ошибка: ' + result.message);
        }
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
});

// Редактировать тариф
document.getElementById('editTariffForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const tariffId = document.getElementById('edit_tariff_id').value;
    const formData = new FormData(e.target);
    const data = {
        name: formData.get('name'),
        lessons_count: formData.get('lessons_count'),
        price: formData.get('price'),
        description: formData.get('description')
    };
    
    try {
        const response = await fetch(`/api/tariffs/${tariffId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert('✓ Тариф обновлён!');
            editTariffModal.style.display = 'none';
            loadTariffs();
        } else {
            alert('Ошибка: ' + result.message);
        }
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
});

// Прикрепить обработчики к кнопкам
function attachTariffButtons() {
    // Редактировать
    document.querySelectorAll('.edit-tariff-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tariffId = btn.getAttribute('data-tariff-id');
            
            try {
                const response = await fetch('/api/tariffs');
                const tariffs = await response.json();
                const tariff = tariffs.find(t => t.id == tariffId);
                
                if (tariff) {
                    document.getElementById('edit_tariff_id').value = tariff.id;
                    document.getElementById('edit_name').value = tariff.name;
                    document.getElementById('edit_lessons_count').value = tariff.lessons_count;
                    document.getElementById('edit_price').value = tariff.price;
                    document.getElementById('edit_description').value = tariff.description || '';
                    
                    editTariffModal.style.display = 'block';
                }
            } catch (error) {
                console.error('Ошибка загрузки тарифа:', error);
            }
        });
    });
    
    // Удалить
    document.querySelectorAll('.delete-tariff-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tariffId = btn.getAttribute('data-tariff-id');
            const tariffName = btn.getAttribute('data-tariff-name');
            
            if (!confirm(`Удалить тариф "${tariffName}"?`)) return;
            
            try {
                const response = await fetch(`/api/tariffs/${tariffId}`, {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (result.success) {
                    alert('✓ ' + result.message);
                    loadTariffs();
                } else {
                    alert('Ошибка: ' + result.message);
                }
            } catch (error) {
                alert('Ошибка: ' + error.message);
            }
        });
    });
}

// Загрузить при открытии страницы (в настройках — при открытии вкладки)
if (!document.body.classList.contains('settings-page')) loadTariffs();
