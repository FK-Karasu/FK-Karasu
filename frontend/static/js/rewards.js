// Безопасный вывод текста в HTML. На странице настроек функция уже есть (settings.js),
// на отдельных страницах групп/тарифов/вознаграждений — объявляем здесь.
if (typeof window.escapeHtml !== 'function') {
    window.escapeHtml = (value) => String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const rewardEditIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const rewardTrashIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>';

// Загрузка вознаграждений
async function loadRewards() {
    try {
        const response = await fetch('/api/rewards');
        if (!response.ok) {
            if (response.status === 403) {
                // Без прав на вознаграждения не выкидываем со страницы — просто показываем, почему пусто.
                const body = document.getElementById('rewardsTableBody');
                if (body) body.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#95a5a6;">Нет прав на просмотр вознаграждений</td></tr>';
                return;
            }
            throw new Error('Ошибка загрузки вознаграждений');
        }
        
        const rewards = await response.json();
        
        const tbody = document.getElementById('rewardsTableBody');
        
        if (rewards.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #95a5a6;">Нет вознаграждений</td></tr>';
            return;
        }
        
        tbody.innerHTML = rewards.map(r => `
            <tr>
                <td><strong>${escapeHtml(r.name)}</strong></td>
                <td><span style="color: #27ae60; font-weight: bold;">${r.points} балл${r.points === 1 ? '' : r.points < 5 ? 'а' : 'ов'}</span></td>
                <td>${r.description ? escapeHtml(r.description) : '-'}</td>
                <td class="action-buttons">
                    <button class="btn-small btn-info edit-reward-btn" data-reward-id="${r.id}" title="Изменить">${rewardEditIcon}</button>
                    <button class="btn-small btn-danger delete-reward-btn" data-reward-id="${r.id}" data-reward-name="${escapeHtml(r.name)}" title="Удалить">${rewardTrashIcon}</button>
                </td>
            </tr>
        `).join('');
        
        // Обработчики кнопок
        attachRewardButtons();
    } catch (error) {
        console.error('Ошибка загрузки вознаграждений:', error);
        alert('Ошибка загрузки вознаграждений: ' + error.message);
    }
}

// Модальные окна - инициализация только если элементы существуют
(function initRewardsModals() {
    const addRewardModal = document.getElementById('addRewardModal');
    const editRewardModal = document.getElementById('editRewardModal');
    const addRewardBtn = document.getElementById('addRewardBtn');
    
    if (!addRewardModal || !editRewardModal || !addRewardBtn) {
        return; // Элементы не найдены, возможно страница не загружена или это другая страница
    }
    
    // Открыть модалку добавления
    addRewardBtn.addEventListener('click', () => {
        addRewardModal.style.display = 'block';
    });
    
    // Закрыть модалки через кнопки закрытия
    const closeBtns = document.querySelectorAll('#addRewardModal .close, #editRewardModal .close');
    closeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            addRewardModal.style.display = 'none';
            editRewardModal.style.display = 'none';
        });
    });
    
    // Закрыть при клике вне модалки
    window.addEventListener('click', (e) => {
        if (e.target === addRewardModal) addRewardModal.style.display = 'none';
        if (e.target === editRewardModal) editRewardModal.style.display = 'none';
    });
})();

// Добавить вознаграждение - инициализация только если форма существует
(function initRewardsForms() {
    const addRewardForm = document.getElementById('addRewardForm');
    const editRewardForm = document.getElementById('editRewardForm');
    const addRewardModal = document.getElementById('addRewardModal');
    const editRewardModal = document.getElementById('editRewardModal');
    
    if (!addRewardForm || !editRewardForm) {
        return; // Формы не найдены
    }
    
    addRewardForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const data = {
            name: formData.get('name').trim(),
            points: parseInt(formData.get('points')),
            description: formData.get('description').trim()
        };
        
        if (!data.name) {
            alert('Название вознаграждения не может быть пустым');
            return;
        }
        
        if (data.points < 1) {
            alert('Количество баллов должно быть больше 0');
            return;
        }
        
        try {
            const response = await fetch('/api/rewards/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('✓ Вознаграждение успешно добавлено!');
                if (addRewardModal) addRewardModal.style.display = 'none';
                e.target.reset();
                loadRewards();
            } else {
                alert('Ошибка: ' + (result.message || 'Не удалось добавить вознаграждение'));
            }
        } catch (error) {
            alert('Ошибка: ' + error.message);
        }
    });
    
    // Редактировать вознаграждение
    editRewardForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const rewardId = document.getElementById('edit_reward_id').value;
        const formData = new FormData(e.target);
        const data = {
            name: formData.get('name').trim(),
            points: parseInt(formData.get('points')),
            description: formData.get('description').trim()
        };
        
        if (!data.name) {
            alert('Название вознаграждения не может быть пустым');
            return;
        }
        
        if (data.points < 1) {
            alert('Количество баллов должно быть больше 0');
            return;
        }
        
        try {
            const response = await fetch(`/api/rewards/${rewardId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('✓ Вознаграждение обновлено!');
                if (editRewardModal) editRewardModal.style.display = 'none';
                loadRewards();
            } else {
                alert('Ошибка: ' + (result.message || 'Не удалось обновить вознаграждение'));
            }
        } catch (error) {
            alert('Ошибка: ' + error.message);
        }
    });
})();

// Прикрепить обработчики к кнопкам
function attachRewardButtons() {
    const editRewardModal = document.getElementById('editRewardModal');
    
    // Редактировать
    document.querySelectorAll('.edit-reward-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const rewardId = btn.getAttribute('data-reward-id');
            
            try {
                const response = await fetch('/api/rewards');
                if (!response.ok) throw new Error('Ошибка загрузки вознаграждений');
                
                const rewards = await response.json();
                const reward = rewards.find(r => r.id == rewardId);
                
                if (reward) {
                    document.getElementById('edit_reward_id').value = reward.id;
                    (document.getElementById('edit_reward_name') || document.getElementById('edit_name')).value = reward.name;
                    (document.getElementById('edit_reward_points') || document.getElementById('edit_points')).value = reward.points;
                    (document.getElementById('edit_reward_description') || document.getElementById('edit_description')).value = reward.description || '';
                    
                    if (editRewardModal) editRewardModal.style.display = 'block';
                }
            } catch (error) {
                console.error('Ошибка загрузки вознаграждения:', error);
                alert('Ошибка загрузки вознаграждения: ' + error.message);
            }
        });
    });
    
    // Удалить
    document.querySelectorAll('.delete-reward-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const rewardId = btn.getAttribute('data-reward-id');
            const rewardName = btn.getAttribute('data-reward-name');
            
            if (!confirm(`Вы уверены, что хотите удалить вознаграждение "${rewardName}"?`)) {
                return;
            }
            
            try {
                const response = await fetch(`/api/rewards/${rewardId}`, {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (result.success) {
                    alert('✓ Вознаграждение удалено!');
                    loadRewards();
                } else {
                    alert('Ошибка: ' + (result.message || 'Не удалось удалить вознаграждение'));
                }
            } catch (error) {
                alert('Ошибка: ' + error.message);
            }
        });
    });
}

// Загрузить вознаграждения при загрузке страницы (только если есть таблица)
document.addEventListener('DOMContentLoaded', () => {
    const rewardsTableBody = document.getElementById('rewardsTableBody');
    if (rewardsTableBody && !document.body.classList.contains('settings-page')) {
        loadRewards();
    }
});


