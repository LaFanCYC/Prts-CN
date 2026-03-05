const API_BASE = 'http://localhost:5000/api';

let currentSubjectId = null;
let currentExamId = null;
let currentQuestions = [];
let currentImage = null;
let imageScale = 1;
let selectedQuestionIndex = null;

async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    console.log('API请求:', url, options);
    
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        console.log('API响应状态:', response.status);
        if (!response.ok) {
            const error = await response.json().catch(() => ({
                error: `HTTP error! status: ${response.status}`
            }));
            throw new Error(error.error || 'Request failed');
        }
        
        const data = await response.json();
        console.log('API响应数据:', data);
        return data;
    } catch (error) {
        console.error('API请求失败:', error);
        throw error;
    }
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId + '-page').classList.add('active');
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`[data-page="${pageId}"]`)?.classList.add('active');
}

function showModal(modalId) {
    document.getElementById(modalId + '-modal').classList.add('active');
}

function hideModal(modalId) {
    document.getElementById(modalId + '-modal').classList.remove('active');
}

async function loadSubjects() {
    try {
        const subjects = await apiRequest('/subjects');
        const grid = document.getElementById('subjects-grid');
        
        if (subjects.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <span style="font-size: 48px;">📚</span>
                    <p>还没有学科，点击"新建学科"开始</p>
                </div>
            `;
            return;
        }
        
        grid.innerHTML = subjects.map(s => `
            <div class="subject-card" data-id="${s.id}">
                <h3>${s.name}</h3>
                <p class="exam-count">${s.exam_count || 0} 场考试</p>
                <div class="card-actions">
                    <button class="btn btn-secondary btn-view-exams" data-id="${s.id}">查看考试</button>
                    <button class="btn btn-secondary btn-delete-subject" data-id="${s.id}">删除</button>
                </div>
            </div>
        `).join('');
        
        grid.querySelectorAll('.btn-view-exams').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                currentSubjectId = parseInt(btn.dataset.id);
                loadExams(currentSubjectId);
            });
        });
        
        grid.querySelectorAll('.btn-delete-subject').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm('确定要删除这个学科吗？')) {
                    await apiRequest(`/subjects/${btn.dataset.id}`, { method: 'DELETE' });
                    loadSubjects();
                }
            });
        });
        
        grid.querySelectorAll('.subject-card').forEach(card => {
            card.addEventListener('click', () => {
                currentSubjectId = parseInt(card.dataset.id);
                loadExams(currentSubjectId);
            });
        });
    } catch (error) {
        console.error('Failed to load subjects:', error);
    }
}

async function loadExams(subjectId) {
    try {
        const subject = await apiRequest(`/subjects/${subjectId}`);
        document.getElementById('current-subject-name').textContent = subject.name;
        
        const exams = await apiRequest(`/subjects/${subjectId}/exams`);
        const grid = document.getElementById('exams-grid');
        
        if (exams.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <span style="font-size: 48px;">📝</span>
                    <p>还没有考试，点击"新建考试"开始</p>
                </div>
            `;
        } else {
            grid.innerHTML = exams.map(e => `
                <div class="exam-card" data-id="${e.id}">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <h3>${e.name}</h3>
                        <button class="btn btn-icon btn-delete-exam" data-id="${e.id}" style="background: #dc2626; color: white; padding: 4px 8px;">×</button>
                    </div>
                    <p class="exam-date">${e.date || '未设置日期'}</p>
                    <div class="exam-stats">
                        <span>${e.question_count || 0} 题</span>
                        <span class="score">${e.user_score || 0} / ${e.total_score || 0} 分</span>
                    </div>
                </div>
            `).join('');
            
            grid.querySelectorAll('.exam-card').forEach(card => {
                card.addEventListener('click', (e) => {
                    if (!e.target.classList.contains('btn-delete-exam')) {
                        currentExamId = parseInt(card.dataset.id);
                        showUploadModalForExam();
                    }
                });
            });
            
            grid.querySelectorAll('.btn-delete-exam').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const examId = parseInt(btn.dataset.id);
                    
                    if (confirm('确定要删除这个考试吗？')) {
                        await apiRequest(`/exams/${examId}`, { method: 'DELETE' });
                        
                        if (currentExamId === examId) {
                            currentExamId = null;
                            currentQuestions = [];
                            currentImage = null;
                            showPage('exams');
                        }
                        
                        loadExams(currentSubjectId);
                    }
                });
            });
        }
        
        showPage('exams');
    } catch (error) {
        console.error('Failed to load exams:', error);
    }
}

async function loadCorrectionWorkspace() {
    try {
        const exam = await apiRequest(`/exams/${currentExamId}`);
        document.getElementById('current-exam-name').textContent = exam.name;
        
        const questions = await apiRequest(`/exams/${currentExamId}/questions`);
        currentQuestions = questions;
        
        if (questions.length > 0 && questions[0].image_path) {
            currentImage = questions[0].image_path;
            loadImageToCanvas(currentImage);
        } else {
            const canvas = document.getElementById('exam-canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = 800;
            canvas.height = 600;
            ctx.fillStyle = '#fafafa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#999';
            ctx.font = '20px -apple-system, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('请上传试卷图片', 400, 300);
        }
        
        renderQuestionsList();
        showPage('correction');
    } catch (error) {
        console.error('Failed to load correction workspace:', error);
    }
}

function showExamActionsModal() {
    showModal('exam-actions');
}

function showUploadModalForExam() {
    showExamActionsModal();
}

function loadImageToCanvas(imagePath) {
    const canvas = document.getElementById('exam-canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    img.onload = () => {
        const container = document.querySelector('.canvas-container');
        const maxWidth = container.clientWidth - 40;
        const maxHeight = container.clientHeight - 40;
        
        let width = img.width;
        let height = img.height;
        
        if (width > maxWidth) {
            height = (maxWidth / width) * height;
            width = maxWidth;
        }
        if (height > maxHeight) {
            width = (maxHeight / height) * width;
            height = maxHeight;
        }
        
        canvas.width = width;
        canvas.height = height;
        imageScale = width / img.width;
        
        ctx.drawImage(img, 0, 0, width, height);
        
        drawQuestionHighlights();
    };
    
    img.src = imagePath;
}

function drawQuestionHighlights() {
    if (selectedQuestionIndex === null) return;
    
    const canvas = document.getElementById('exam-canvas');
    const ctx = canvas.getContext('2d');
    const question = currentQuestions[selectedQuestionIndex];
    
    if (!question || !question.coordinates || question.coordinates.length !== 4) return;
    
    const [x, y, w, h] = question.coordinates;
    
    ctx.strokeStyle = '#2563eb';
    ctx.lineWidth = 3;
    ctx.strokeRect(x * imageScale, y * imageScale, w * imageScale, h * imageScale);
    
    ctx.fillStyle = 'rgba(37, 99, 235, 0.2)';
    ctx.fillRect(x * imageScale, y * imageScale, w * imageScale, h * imageScale);
}

function renderQuestionsList() {
    const list = document.getElementById('questions-list');
    
    if (currentQuestions.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <span style="font-size: 48px;">📄</span>
                <p>还没有题目，请先上传试卷</p>
            </div>
        `;
        return;
    }
    
    list.innerHTML = currentQuestions.map((q, index) => `
        <div class="question-item" data-index="${index}">
            <div class="question-header">
                <span class="question-index">第 ${q.question_index} 题</span>
                <div class="question-score">
                    <input type="number" class="max-score-input" 
                           value="${q.max_score || 10}" 
                           data-field="max_score"
                           data-index="${index}"
                           min="0" step="0.5"> 分
                </div>
            </div>
            <div class="question-text">${q.ocr_text || '未识别到题干'}</div>
            <textarea class="answer-input" 
                      placeholder="请输入作答内容..." 
                      data-field="user_answer_text"
                      data-index="${index}">${q.user_answer_text || ''}</textarea>
            ${q.user_score !== null ? `
                <div class="question-result">
                    <div class="score-display">
                        <span>得分：</span>
                        <span class="score-value">${q.user_score} / ${q.max_score}</span>
                    </div>
                    ${q.feedback ? `<p class="feedback-text">${q.feedback}</p>` : ''}
                </div>
            ` : ''}
        </div>
    `).join('');
    
    list.querySelectorAll('.question-item').forEach(item => {
        item.addEventListener('click', () => {
            const index = parseInt(item.dataset.index);
            selectQuestion(index);
        });
    });
    
    list.querySelectorAll('.max-score-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const value = parseFloat(e.target.value) || 10;
            
            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ max_score: value })
            });
            
            currentQuestions[index].max_score = value;
        });
        
        input.addEventListener('click', (e) => e.stopPropagation());
    });
    
    list.querySelectorAll('.answer-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const value = e.target.value;
            
            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ user_answer_text: value })
            });
            
            currentQuestions[index].user_answer_text = value;
        });
        
        input.addEventListener('click', (e) => e.stopPropagation());
    });
}

function selectQuestion(index) {
    selectedQuestionIndex = index;
    
    document.querySelectorAll('.question-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
    
    if (currentImage) {
        const canvas = document.getElementById('exam-canvas');
        const ctx = canvas.getContext('2d');
        const img = new Image();
        
        img.onload = () => {
            const container = document.querySelector('.canvas-container');
            const maxWidth = container.clientWidth - 40;
            const maxHeight = container.clientHeight - 40;
            
            let width = img.width;
            let height = img.height;
            
            if (width > maxWidth) {
                height = (maxWidth / width) * height;
                width = maxWidth;
            }
            if (height > maxHeight) {
                width = (maxHeight / height) * width;
                height = maxHeight;
            }
            
            canvas.width = width;
            canvas.height = height;
            imageScale = width / img.width;
            
            ctx.drawImage(img, 0, 0, width, height);
            drawQuestionHighlights();
        };
        
        img.src = currentImage;
    }
    
    const questionItem = document.querySelector(`.question-item[data-index="${index}"]`);
    questionItem?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function loadDashboard() {
    try {
        const subjects = await apiRequest('/subjects');
        const select = document.getElementById('dashboard-subject-select');
        
        select.innerHTML = subjects.map(s => 
            `<option value="${s.id}">${s.name}</option>`
        ).join('');
        
        if (subjects.length > 0) {
            await loadDashboardData(subjects[0].id);
        }
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

async function loadDashboardData(subjectId) {
    try {
        const data = await apiRequest(`/dashboard/${subjectId}`);
        
        renderTrendChart(data.exams);
        renderRateChart(data.exams);
        
        const analysis = document.getElementById('exam-analysis');
        if (data.exams.length === 0) {
            analysis.innerHTML = '<p>暂无考试数据</p>';
        }
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
    }
}

function renderTrendChart(exams) {
    const chart = echarts.init(document.getElementById('trend-chart'));
    
    const dates = exams.map(e => e.date);
    const scores = exams.map(e => e.user_score);
    const totals = exams.map(e => e.total_score);
    
    chart.setOption({
        tooltip: {
            trigger: 'axis'
        },
        legend: {
            data: ['得分', '总分']
        },
        xAxis: {
            type: 'category',
            data: dates
        },
        yAxis: {
            type: 'value'
        },
        series: [
            {
                name: '得分',
                type: 'line',
                data: scores,
                itemStyle: { color: '#1a1a1a' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(26, 26, 26, 0.3)' },
                        { offset: 1, color: 'rgba(26, 26, 26, 0.05)' }
                    ])
                }
            },
            {
                name: '总分',
                type: 'line',
                data: totals,
                lineStyle: { type: 'dashed' },
                itemStyle: { color: '#999' }
            }
        ]
    });
}

function renderRateChart(exams) {
    const chart = echarts.init(document.getElementById('rate-chart'));
    
    const data = exams.map(e => ({
        name: e.name,
        value: e.score_rate
    }));
    
    chart.setOption({
        tooltip: {
          trigger: 'item',
          formatter: '{b}: {c}%'
        },
        series: [
            {
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderRadius: 4,
                    borderColor: '#fff',
                    borderWidth: 2
                },
                label: {
                    show: false
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 14,
                        fontWeight: 'bold'
                    }
                },
                data: data.map((d, i) => ({
                    ...d,
                    itemStyle: { color: ['#1a1a1a', '#666', '#999', '#ccc'][i % 4] }
                }))
            }
        ]
    });
}

async function loadPrompts() {
    try {
        const prompts = await apiRequest('/prompts');
        const list = document.getElementById('prompts-list');
        
        list.innerHTML = `
            <h3>可用 Prompts</h3>
            ${prompts.map(p => `
                <div class="prompt-item" data-id="${p.id}" data-name="${p.name}">
                    <h4>${p.role || p.name}</h4>
                    <p>${p.description}</p>
                </div>
            `).join('')}
        `;
        
        list.querySelectorAll('.prompt-item').forEach(item => {
            item.addEventListener('click', () => {
                const prompt = prompts.find(p => p.id === parseInt(item.dataset.id));
                showPromptEditor(prompt);
            });
        });
        
        if (prompts.length > 0) {
            showPromptEditor(prompts[0]);
        }
    } catch (error) {
        console.error('Failed to load prompts:', error);
    }
}

function showPromptEditor(prompt) {
    document.querySelectorAll('.prompt-item').forEach(item => {
        item.classList.toggle('active', parseInt(item.dataset.id) === prompt.id);
    });
    
    document.getElementById('editor-title').textContent = `编辑 ${prompt.role || prompt.name}`;
    document.getElementById('prompt-role').value = prompt.role || '';
    document.getElementById('prompt-description').value = prompt.description || '';
    document.getElementById('prompt-content').value = prompt.system_prompt || '';
    
    window.currentPromptId = prompt.id;
}

async function savePrompt() {
    try {
        await apiRequest(`/prompts/${window.currentPromptId}`, {
            method: 'PUT',
            body: JSON.stringify({
                role: document.getElementById('prompt-role').value,
                description: document.getElementById('prompt-description').value,
                system_prompt: document.getElementById('prompt-content').value
            })
        });
        
        alert('保存成功！');
    } catch (error) {
        console.error('Failed to save prompt:', error);
        alert('保存失败：' + error.message);
    }
}

async function resetPrompt() {
    if (!confirm('确定要重置为默认Prompt吗？')) return;
    
    try {
        const prompt = await apiRequest(`/prompts/${window.currentPromptId}/reset`, {
            method: 'POST'
        });
        
        document.getElementById('prompt-content').value = prompt.system_prompt;
        alert('已重置为默认Prompt');
    } catch (error) {
        console.error('Failed to reset prompt:', error);
    }
}

async function loadSettings() {
    try {
        const settings = await apiRequest('/settings');
        document.getElementById('api-key').value = settings.api_key || '';
        document.getElementById('api-base').value = settings.api_base || '';
        document.getElementById('model-vision').value = settings.model_vision || '';
        document.getElementById('model-grading').value = settings.model_grading || '';
        document.getElementById('model-analysis').value = settings.model_analysis || '';
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

async function saveSettings() {
    const settings = {
        api_key: document.getElementById('api-key').value,
        api_base: document.getElementById('api-base').value,
        model_vision: document.getElementById('model-vision').value,
        model_grading: document.getElementById('model-grading').value,
        model_analysis: document.getElementById('model-analysis').value
    };
    
    try {
        await apiRequest('/settings', {
            method: 'PUT',
            body: JSON.stringify(settings)
        });
        alert('设置保存成功！');
    } catch (error) {
        console.error('Failed to save settings:', error);
        alert('保存失败：' + error.message);
    }
}

async function resetSettings() {
    if (!confirm('确定要重置为默认设置吗？')) return;
    
    try {
        await apiRequest('/settings/reset', {
            method: 'POST'
        });
        await loadSettings();
        alert('已重置为默认设置');
    } catch (error) {
        console.error('Failed to reset settings:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            showPage(page);
            
            if (page === 'subjects') loadSubjects();
            if (page === 'dashboard') loadDashboard();
            if (page === 'prompts') loadPrompts();
            if (page === 'settings') loadSettings();
        });
    });
    
    document.getElementById('add-subject-btn').addEventListener('click', () => {
        document.getElementById('subject-name').value = '';
        showModal('subject');
    });
    
    document.getElementById('save-subject-btn').addEventListener('click', async () => {
        const name = document.getElementById('subject-name').value.trim();
        if (!name) return;
        
        await apiRequest('/subjects', {
            method: 'POST',
            body: JSON.stringify({ name })
        });
        
        hideModal('subject');
        loadSubjects();
    });
    
    document.getElementById('cancel-subject-btn').addEventListener('click', () => hideModal('subject'));
    
    document.getElementById('back-to-subjects').addEventListener('click', () => {
        showPage('subjects');
    });
    
    document.getElementById('add-exam-btn').addEventListener('click', () => {
        document.getElementById('exam-name').value = '';
        document.getElementById('exam-date').value = new Date().toISOString().split('T')[0];
        showModal('exam');
    });
    
    document.getElementById('save-exam-btn').addEventListener('click', async () => {
        const name = document.getElementById('exam-name').value.trim();
        const date = document.getElementById('exam-date').value;
        
        if (!name) return;
        
        await apiRequest('/exams', {
            method: 'POST',
            body: JSON.stringify({
                subject_id: currentSubjectId,
                name,
                date
            })
        });
        
        hideModal('exam');
        loadExams(currentSubjectId);
    });
    
    document.getElementById('cancel-exam-btn').addEventListener('click', () => hideModal('exam'));
    
    document.getElementById('back-to-exams').addEventListener('click', () => {
        showPage('exams');
    });
    
    document.getElementById('upload-btn').addEventListener('click', () => {
        showModal('upload');
    });
    
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    
    uploadArea.addEventListener('click', () => fileInput.click());
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '#1a1a1a';
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.style.borderColor = '#e5e5e5';
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '#e5e5e5';
        
        const files = e.dataTransfer.files;
        if (files.length > 0) uploadFile(files);
    });
    
    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) uploadFile(files);
    });
    
    async function uploadFile(files) {
        const filesArray = Array.from(files);
        let uploadedCount = 0;
        const totalFiles = filesArray.length;
        
        document.getElementById('upload-area').style.display = 'none';
        document.getElementById('upload-progress').style.display = 'block';
        
        try {
            for (let i = 0; i < totalFiles; i++) {
                const file = filesArray[i];
                const formData = new FormData();
                formData.append('file', file);
                formData.append('exam_id', currentExamId);
                formData.append('extract', 'false'); // 不上传时自动提取题目
                
                console.log('上传文件:', file.name, '到', `${API_BASE}/upload`);
                const response = await fetch(`${API_BASE}/upload`, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'Accept': 'application/json'
                    }
                });
                
                console.log('上传响应状态:', response.status);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const result = await response.json();
                console.log('上传响应结果:', result);
                
                // 只保存图片路径，不提取题目
                if (result.image_path) {
                    currentImage = result.image_path;
                    // 创建一个默认题目
                    const defaultQuestion = {
                        id: result.questions ? result.questions[0].id : null,
                        question_index: '1',
                        ocr_text: '请点击"提取题目"按钮提取题目',
                        image_path: result.image_path
                    };
                    currentQuestions = [defaultQuestion];
                }
                
                uploadedCount++;
                const progress = (uploadedCount / totalFiles) * 100;
                document.querySelector('.progress-fill').style.width = `${progress}%`;
            }
            
            loadCorrectionWorkspace();
            hideModal('upload');
        } catch (error) {
            console.error('上传失败:', error);
            alert('上传失败：' + error.message);
        } finally {
            document.getElementById('upload-area').style.display = 'block';
            document.getElementById('upload-progress').style.display = 'none';
            document.querySelector('.progress-fill').style.width = '0%';
        }
    }
    
    // 提取题目函数
    async function extractQuestions() {
        if (!currentImage) {
            alert('请先上传试卷图片');
            return;
        }
        
        const btn = document.getElementById('extract-questions-btn');
        btn.disabled = true;
        btn.textContent = '提取中...';
        
        try {
            console.log('开始提取题目，图片路径:', currentImage);
            
            // 构建请求数据
            const formData = new FormData();
            formData.append('image_path', currentImage);
            formData.append('exam_id', currentExamId);
            formData.append('extract', 'true');
            
            const response = await fetch(`${API_BASE}/extract-questions`, {
                method: 'POST',
                body: formData,
                headers: {
                    'Accept': 'application/json'
                }
            });
            
            console.log('提取题目响应状态:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            console.log('提取题目响应结果:', result);
            
            if (result.error) {
                alert('分析失败：' + result.error);
                return;
            }
            
            if (result.questions && result.questions.length > 0) {
                currentQuestions = result.questions;
                renderQuestionsList();
                alert('题目提取完成！');
            } else {
                alert('未检测到题目，请检查图片是否清晰');
            }
        } catch (error) {
            console.error('提取题目失败:', error);
            alert('分析失败：' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '提取题目';
        }
    }
    
    document.getElementById('cancel-upload-btn').addEventListener('click', () => {
        hideModal('upload');
        document.getElementById('upload-area').style.display = 'block';
        document.getElementById('upload-progress').style.display = 'none';
    });
    
    document.getElementById('action-upload').addEventListener('click', () => {
        hideModal('exam-actions');
        showModal('upload');
    });
    
    document.getElementById('action-edit').addEventListener('click', () => {
        hideModal('exam-actions');
        loadCorrectionWorkspace();
    });
    
    document.getElementById('action-analysis').addEventListener('click', () => {
        hideModal('exam-actions');
        showPage('dashboard');
        if (currentSubjectId) {
            const select = document.getElementById('dashboard-subject-select');
            if (select) {
                select.value = currentSubjectId;
                loadDashboardData(currentSubjectId);
            }
        }
    });
    
    document.getElementById('cancel-exam-actions').addEventListener('click', () => {
        hideModal('exam-actions');
    });
    
    document.getElementById('extract-questions-btn').addEventListener('click', extractQuestions);
    
    document.getElementById('start-grading-btn').addEventListener('click', async () => {
        if (currentQuestions.length === 0) {
            alert('请先上传试卷');
            return;
        }
        
        const btn = document.getElementById('start-grading-btn');
        btn.disabled = true;
        btn.textContent = '批改中...';
        
        try {
            console.log('开始批改，请求URL:', `${API_BASE}/grade-all/${currentExamId}`);
            const gradedQuestions = await apiRequest(`/grade-all/${currentExamId}`, {
                method: 'POST'
            });
            
            console.log('批改完成，返回结果:', gradedQuestions);
            currentQuestions = gradedQuestions;
            renderQuestionsList();
            
            alert('批改完成！');
        } catch (error) {
            console.error('批改失败:', error);
            alert('批改失败：' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '开始批改';
        }
    });
    
    document.getElementById('save-prompt-btn').addEventListener('click', savePrompt);
    document.getElementById('reset-prompt-btn').addEventListener('click', resetPrompt);
    
    document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
    document.getElementById('reset-settings-btn').addEventListener('click', resetSettings);
    
    document.getElementById('dashboard-subject-select').addEventListener('change', (e) => {
        loadDashboardData(parseInt(e.target.value));
    });
    
    loadSubjects();
});
