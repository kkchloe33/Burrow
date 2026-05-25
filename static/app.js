// Burrow 兔子洞 - 前端逻辑
const API = '/api';

// ==================== 状态 ====================
let currentView = 'home';     // home | list | detail
let currentType = null;
let currentPeriod = 'all';
let allTypes = [];

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    setTodayDate();
    loadHome();

    // 事件绑定
    document.getElementById('homeBtn').addEventListener('click', () => loadHome());
    document.getElementById('addBtn').addEventListener('click', openAddModal);
    document.getElementById('btnCancel').addEventListener('click', closeAddModal);
    document.getElementById('btnSave').addEventListener('click', saveEntry);

    // 点击遮罩关闭
    document.getElementById('addModal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeAddModal();
    });
    document.getElementById('detailModal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeDetailModal();
    });

    // 重要度滑块实时显示
    const impSlider = document.getElementById('formImportance');
    impSlider.addEventListener('input', () => {
        document.getElementById('impVal').textContent = impSlider.value;
    });
});

function setTodayDate() {
    const now = new Date();
    const days = ['日','一','二','三','四','五','六'];
    const str = `${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 星期${days[now.getDay()]}`;
    document.getElementById('todayDate').textContent = str;
}

// ==================== API 调用 ====================

async function apiGet(path) {
    const res = await fetch(`${API}${path}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

async function apiPost(path, data) {
    const res = await fetch(`${API}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

async function apiPut(path, data) {
    const res = await fetch(`${API}${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

async function apiDelete(path) {
    const res = await fetch(`${API}${path}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// ==================== 首页 ====================

async function loadHome() {
    currentView = 'home';
    currentType = null;
    document.getElementById('mainContent').innerHTML = '<div class="empty-state"><p>加载中...</p></div>';

    try {
        const types = await apiGet('/types');
        allTypes = types;
        const permanent = await apiGet('/permanent');
        renderHome(types, permanent);
    } catch (e) {
        document.getElementById('mainContent').innerHTML = `<div class="empty-state"><p>加载失败: ${e.message}</p></div>`;
    }
}

function renderHome(types, permanent) {
    const main = document.getElementById('mainContent');

    // 类型卡片
    let html = '<div class="home-grid">';
    for (const t of types) {
        const colorClass = `color-${t.type}`;
        const floatBadge = t.floats_in_default ? '<span class="float-badge">浮动</span>' : '';
        html += `
            <div class="type-card" data-type="${t.type}" onclick="openList('${t.type}')">
                ${floatBadge}
                <div class="icon">${t.icon}</div>
                <div class="label">${t.label}</div>
                <div class="count">${t.count || 0}条</div>
                <div class="color-bar ${colorClass}"></div>
            </div>`;
    }
    // 全部记忆
    const total = types.reduce((s, t) => s + (t.count || 0), 0);
    html += `
        <div class="type-card card-all" onclick="openList('')">
            <div class="icon">📦</div>
            <div class="label">全部记忆</div>
            <div class="count">${total}条</div>
        </div>`;
    html += '</div>';

    // 永久记忆区
    if (permanent.length > 0) {
        html += '<div class="permanent-section">';
        html += '<div class="section-title">★ 永久记忆</div>';
        html += '<div class="permanent-row">';
        for (const p of permanent) {
            html += `
                <div class="permanent-card" onclick="openDetail('${p.id}')">
                    <div class="p-type">${getTypeLabel(p.type)}</div>
                    <div class="p-title">${escapeHtml(p.title || p.content.slice(0,20))}</div>
                </div>`;
        }
        html += '</div></div>';
    }

    main.innerHTML = html;
}

// ==================== 列表页 ====================

async function openList(type) {
    currentView = 'list';
    currentType = type;
    currentPeriod = 'all';

    const label = type ? getTypeLabel(type) : '全部记忆';
    const main = document.getElementById('mainContent');
    main.innerHTML = `
        <div class="list-page">
            <div class="list-header">
                <span class="back-btn" onclick="loadHome()">←</span>
                <span class="list-title">${label}</span>
                <button class="add-type-btn" onclick="openAddModal('${type || ''}')">+新增</button>
            </div>
            <div class="filter-bar">
                <span class="filter-chip active" data-period="all" onclick="switchPeriod('all')">全部</span>
                <span class="filter-chip" data-period="week" onclick="switchPeriod('week')">本周</span>
                <span class="filter-chip" data-period="month" onclick="switchPeriod('month')">本月</span>
            </div>
            <div class="timeline" id="timeline">加载中...</div>
        </div>`;

    await loadEntries();
}

async function switchPeriod(period) {
    currentPeriod = period;
    document.querySelectorAll('.filter-chip').forEach(c => {
        c.classList.toggle('active', c.dataset.period === period);
    });
    await loadEntries();
}

async function loadEntries() {
    const timeline = document.getElementById('timeline');
    if (!timeline) return;

    try {
        let url = `/entries?`;
        if (currentType) url += `type=${currentType}&`;
        url += `period=${currentPeriod}`;

        let entries = await apiGet(url);

        // 如果是指定类型，需要前端过滤（后端 recall 按 type 参数处理）
        // 后端 /api/entries 已按 type 过滤
        if (currentPeriod !== 'all') {
            const now = new Date();
            let cutoff;
            if (currentPeriod === 'today') cutoff = new Date(now - 86400000);
            else if (currentPeriod === 'week') cutoff = new Date(now - 7 * 86400000);
            else if (currentPeriod === 'month') cutoff = new Date(now - 30 * 86400000);
            if (cutoff) {
                entries = entries.filter(e => new Date(e.created_at) >= cutoff);
            }
        }

        if (entries.length === 0) {
            timeline.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📭</div>
                    <p>这里还没有记忆</p>
                    <p style="font-size:12px;margin-top:4px;">点击右下角 + 或右上角按钮添加</p>
                </div>`;
            return;
        }

        // 按日期分组
        const groups = {};
        for (const e of entries) {
            const day = e.created_at.slice(0, 10);
            if (!groups[day]) groups[day] = [];
            groups[day].push(e);
        }

        let html = '';
        for (const [day, items] of Object.entries(groups)) {
            html += `<div class="date-group"><div class="date-label">${formatDate(day)}</div>`;
            for (const e of items) {
                html += renderEntryCard(e);
            }
            html += '</div>';
        }
        timeline.innerHTML = html;

    } catch (e) {
        timeline.innerHTML = `<div class="empty-state"><p>加载失败</p></div>`;
    }
}

function renderEntryCard(e) {
    const permClass = e.is_permanent ? ' permanent' : '';
    const star = e.is_permanent ? '<span class="star-badge">⭐</span>' : '';
    const typeLabel = getTypeLabel(e.type);
    const timeStr = relativeTime(e.created_at);
    const title = e.title || e.content.slice(0, 30);
    const preview = e.title ? e.content.slice(0, 80) : '';
    const tags = e.tags ? e.tags.split(',').slice(0, 5) : [];
    const tagsHtml = tags.map(t => `<span class="tag">${t.trim()}</span>`).join('');

    // 结构化字段摘要
    let fieldsHtml = '';
    if (e.fields && e.fields !== '{}') {
        try {
            const f = typeof e.fields === 'string' ? JSON.parse(e.fields) : e.fields;
            const parts = [];
            if (f.weather) parts.push(getWeatherEmoji(f.weather) + f.weather);
            if (f.mood) parts.push(getMoodEmoji(f.mood) + f.mood);
            if (f.rating) parts.push('★'.repeat(f.rating));
            if (f.top) parts.push(f.top);
            if (f.meal) parts.push(f.meal);
            if (parts.length > 0) fieldsHtml = `<div class="card-fields">${parts.join(' · ')}</div>`;
        } catch(_) {}
    }

    return `
        <div class="entry-card${permClass}" onclick="openDetail('${e.id}')">
            ${star}
            <div class="card-header">
                <span class="type-tag tag-${e.type}">${typeLabel}</span>
                <span class="card-time">${timeStr}</span>
            </div>
            <div class="card-title">${escapeHtml(title)}</div>
            ${preview ? `<div class="card-preview">${escapeHtml(preview)}</div>` : ''}
            ${fieldsHtml}
            ${tagsHtml ? `<div class="card-tags">${tagsHtml}</div>` : ''}
        </div>`;
}

// ==================== 详情弹窗 ====================

async function openDetail(id) {
    try {
        const e = await apiGet(`/entries/${id}`);
        const modal = document.getElementById('detailModal');
        const content = document.getElementById('detailContent');

        let fieldsObj = {};
        try { fieldsObj = typeof e.fields === 'string' ? JSON.parse(e.fields) : e.fields; } catch(_) {}

        // 结构化字段
        let fieldsHtml = '';
        const fieldEntries = Object.entries(fieldsObj).filter(([k,v]) => v !== '' && v !== null && v !== 0 && !(Array.isArray(v) && v.length === 0));
        if (fieldEntries.length > 0) {
            fieldsHtml = '<div class="detail-fields">';
            for (const [k, v] of fieldEntries) {
                let display = Array.isArray(v) ? v.join(', ') : v;
                if (k === 'rating') display = '★'.repeat(v) + '☆'.repeat(5-v);
                if (k === 'flow') display = ['','少量','正常','较多','很多'][v] || v;
                if (k === 'weather') display = getWeatherEmoji(v) + ' ' + v;
                if (k === 'mood') display = getMoodEmoji(v) + ' ' + v;
                fieldsHtml += `<div class="field-row"><span class="field-key">${fieldLabel(k)}</span><span>${display}</span></div>`;
            }
            fieldsHtml += '</div>';
        }

        // 标签
        const tags = e.tags ? e.tags.split(',').map(t => `#${t.trim()}`).join(' ') : '';

        const permIcon = e.is_permanent ? '⭐ ' : '';
        const archivedMark = e.is_archived ? ' [已归档]' : '';

        content.innerHTML = `
            <div class="detail-type">
                <span class="type-tag tag-${e.type}">${getTypeLabel(e.type)}</span>
                ${archivedMark}
            </div>
            <div class="detail-title">${permIcon}${escapeHtml(e.title || '无标题')}</div>
            <div class="detail-content">${escapeHtml(e.content)}</div>
            ${fieldsHtml}
            ${tags ? `<div class="detail-tags" style="font-size:13px;color:var(--accent)">${escapeHtml(tags)}</div>` : ''}
            <div class="detail-meta">
                <span>创建: ${e.created_at.slice(0,10)}</span>
                <span>重要度: ${'★'.repeat(e.importance)}${'☆'.repeat(10-e.importance)}</span>
                <span>ID: ${e.id}</span>
            </div>
            <div class="detail-actions">
                <button class="btn btn-primary" onclick="togglePermanent('${e.id}', ${!e.is_permanent})">${e.is_permanent ? '取消永久' : '设为永久记忆'}</button>
                <button class="btn btn-danger" onclick="archiveEntry('${e.id}')">归档</button>
                <button class="btn btn-secondary" onclick="closeDetailModal()">关闭</button>
            </div>`;

        modal.classList.add('show');
    } catch (e) {
        alert('加载失败: ' + e.message);
    }
}

function closeDetailModal() {
    document.getElementById('detailModal').classList.remove('show');
}

async function togglePermanent(id, set) {
    try {
        await apiPut(`/entries/${id}`, { is_permanent: set ? 1 : 0 });
        closeDetailModal();
        refreshCurrent();
    } catch(e) { alert('操作失败'); }
}

async function archiveEntry(id) {
    if (!confirm('确定归档这条记忆吗？归档后仍可搜索到。')) return;
    try {
        await apiPut(`/entries/${id}`, { is_archived: 1 });
        closeDetailModal();
        refreshCurrent();
    } catch(e) { alert('操作失败'); }
}

// ==================== 新增弹窗 ====================

let addSelectedType = null;

async function openAddModal(presetType) {
    addSelectedType = presetType || null;
    const modal = document.getElementById('addModal');
    const stepType = document.getElementById('stepType');
    const stepForm = document.getElementById('stepForm');
    const modalTitle = document.getElementById('modalTitle');

    // 加载类型列表
    if (allTypes.length === 0) {
        try { allTypes = await apiGet('/types'); } catch(_) {}
    }

    stepType.innerHTML = allTypes.map(t => `
        <div class="type-option${t.type === presetType ? ' selected' : ''}" data-type="${t.type}" onclick="selectAddType('${t.type}')">
            <span class="icon-sm">${t.icon}</span>
            ${t.label}
        </div>`).join('');

    if (presetType) {
        // 直接跳到表单
        showAddForm(presetType);
        modalTitle.textContent = `新增 ${getTypeLabel(presetType)}`;
    } else {
        stepType.style.display = '';
        stepForm.style.display = 'none';
        modalTitle.textContent = '新增记忆';
    }

    modal.classList.add('show');
}

function selectAddType(type) {
    addSelectedType = type;
    document.querySelectorAll('.type-option').forEach(o => o.classList.toggle('selected', o.dataset.type === type));
    showAddForm(type);
    document.getElementById('modalTitle').textContent = `新增 ${getTypeLabel(type)}`;
}

function showAddForm(type) {
    document.getElementById('stepType').style.display = 'none';
    document.getElementById('stepForm').style.display = '';

    // 清空表单
    document.getElementById('formTitle').value = '';
    document.getElementById('formContent').value = '';
    document.getElementById('formImportance').value = 5;
    document.getElementById('impVal').textContent = '5';
    document.getElementById('formPermanent').checked = false;

    // 动态字段
    const fieldsDiv = document.getElementById('formFields');
    const schema = getFieldsSchema(type);
    if (schema) {
        let html = '';
        for (const [key, label] of Object.entries(schema)) {
            if (key === 'done') {
                html += `<label class="checkbox-label" style="margin-bottom:10px">
                    <input type="checkbox" class="input" data-field="${key}" style="width:auto"> ${label}
                </label>`;
            } else {
                html += `<input type="text" class="input" data-field="${key}" placeholder="${label}">`;
            }
        }
        fieldsDiv.innerHTML = html;
        fieldsDiv.style.display = '';
    } else {
        fieldsDiv.innerHTML = '';
        fieldsDiv.style.display = 'none';
    }
}

function getFieldsSchema(type) {
    const schemas = {
        outfit: { top:'上装', bottom:'下装', shoes:'鞋子', accessories:'配饰', weather:'天气', mood:'心情', occasion:'场合' },
        diet:   { meal:'餐别', foods:'食物', drink:'饮品', location:'地点', with_who:'同行人', rating:'评分(1-5)' },
        period: { start_date:'开始日期', end_date:'结束日期', flow:'流量(1-4)', symptoms:'症状', mood:'心情', notes:'备注' },
        bowel:  { time:'时间', consistency:'性状(正常/稀/干)', color:'颜色', note:'备注' },
        todo:   { done:'已完成' },
    };
    return schemas[type] || null;
}

async function saveEntry() {
    const content = document.getElementById('formContent').value.trim();
    if (!content) { alert('请输入内容'); return; }

    const type = addSelectedType || 'journal';
    const title = document.getElementById('formTitle').value.trim();
    const importance = parseInt(document.getElementById('formImportance').value);
    const is_permanent = document.getElementById('formPermanent').checked;

    // 收集结构化字段
    const fields = {};
    document.querySelectorAll('#formFields .input').forEach(inp => {
        const key = inp.dataset.field;
        if (inp.type === 'checkbox') {
            fields[key] = inp.checked;
        } else {
            const val = inp.value.trim();
            if (val) {
                if (key === 'rating' || key === 'flow') fields[key] = parseInt(val) || 0;
                else if (key === 'foods' || key === 'symptoms') fields[key] = val.split(/[,，]/).map(s => s.trim()).filter(Boolean);
                else fields[key] = val;
            }
        }
    });

    try {
        await apiPost('/entries', { content, type, title, fields, importance, is_permanent });
        closeAddModal();
        refreshCurrent();
    } catch(e) { alert('保存失败: ' + e.message); }
}

function closeAddModal() {
    document.getElementById('addModal').classList.remove('show');
    addSelectedType = null;
}

// ==================== 工具函数 ====================

function refreshCurrent() {
    if (currentView === 'home') loadHome();
    else if (currentView === 'list') loadEntries();
}

function getTypeLabel(type) {
    const t = allTypes.find(x => x.type === type);
    return t ? t.label : type;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function relativeTime(dateStr) {
    const now = new Date();
    const date = new Date(dateStr);
    const diff = now - date;
    const min = Math.floor(diff / 60000);
    const hr = Math.floor(diff / 3600000);
    const day = Math.floor(diff / 86400000);

    if (min < 1) return '刚刚';
    if (min < 60) return `${min}分钟前`;
    if (hr < 24) return `${hr}小时前`;
    if (day < 7) return `${day}天前`;
    return dateStr.slice(0, 10);
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - d) / 86400000);

    if (diff === 0) return '今天';
    if (diff === 1) return '昨天';
    if (diff === 2) return '前天';
    return dateStr;
}

function getWeatherEmoji(w) {
    const map = { '晴':'☀️','多云':'⛅','阴':'☁️','雨':'🌧️','雪':'❄️','风':'🌬️' };
    for (const [k,v] of Object.entries(map)) {
        if (w.includes(k)) return v;
    }
    return '';
}

function getMoodEmoji(m) {
    const map = { '开心':'😊','快乐':'😄','兴奋':'🤩','平静':'😌','普通':'😐','难过':'😢','生气':'😠','焦虑':'😰','累':'😴' };
    for (const [k,v] of Object.entries(map)) {
        if (m.includes(k)) return v;
    }
    return '';
}

function fieldLabel(key) {
    const map = {
        top:'上装', bottom:'下装', shoes:'鞋子', accessories:'配饰', weather:'天气', mood:'心情', occasion:'场合',
        meal:'餐别', foods:'食物', drink:'饮品', location:'地点', with_who:'同行人', rating:'评分',
        start_date:'开始', end_date:'结束', flow:'流量', symptoms:'症状', notes:'备注',
        time:'时间', consistency:'性状', color:'颜色', note:'备注',
    };
    return map[key] || key;
}
