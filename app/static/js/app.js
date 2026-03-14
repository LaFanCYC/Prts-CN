const API_BASE = 'http://127.0.0.1:5000/api';

let currentSubjectId = null;
let currentExamId = null;
let currentQuestions = [];
let currentImage = null;
let currentImageList = [];
let currentImageIndex = 0;
let imageScale = 1;
let selectedQuestionIndex = null;

let processingExams = {};
let processingSubjects = {};
let cancelGradingRequest = false;
let cancelExtractRequest = false;

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

function getExamStatusText(examId) {
    const status = processingExams[examId];
    if (!status) return '';
    
    const parts = [];
    if (status.extracting) parts.push('提取中');
    if (status.grading) parts.push('批改中');
    if (status.analyzing) parts.push('分析中');
    
    return parts.join(' / ');
}

function updateExamCardStatus(examId) {
    const cards = document.querySelectorAll(`.exam-card[data-id="${examId}"]`);
    cards.forEach(card => {
        const statusEl = card.querySelector('.exam-status');
        const statusText = getExamStatusText(examId);
        
        if (statusText) {
            if (statusEl) {
                statusEl.textContent = statusText;
            } else {
                const dateEl = card.querySelector('.exam-date');
                if (dateEl) {
                    const newStatus = document.createElement('p');
                    newStatus.className = 'exam-status';
                    newStatus.style.cssText = 'color: #f59e0b; font-size: 12px;';
                    newStatus.textContent = statusText;
                    dateEl.parentNode.insertBefore(newStatus, dateEl.nextSibling);
                }
            }
        } else if (statusEl) {
            statusEl.remove();
        }
    });
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
        
        grid.innerHTML = subjects.map(s => {
            const isAnalyzing = processingSubjects[s.id];
            return `
            <div class="subject-card" data-id="${s.id}">
                <h3>${s.name}</h3>
                <p class="exam-count">${s.exam_count || 0} 场考试</p>
                <div class="card-actions">
                    <button class="btn btn-secondary btn-view-exams" data-id="${s.id}">查看考试</button>
                    <button class="btn btn-secondary btn-analyze-subject" data-id="${s.id}" ${isAnalyzing ? 'disabled' : ''}>${isAnalyzing ? '分析中...' : '生成学科分析'}</button>
                    <button class="btn btn-secondary btn-delete-subject" data-id="${s.id}">删除</button>
                </div>
            </div>
        `}).join('');
        
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
        
        grid.querySelectorAll('.btn-analyze-subject').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await generateAnalysisForSubject(parseInt(btn.dataset.id));
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
            grid.innerHTML = exams.map(e => {
                const status = getExamStatusText(e.id);
                return `
                <div class="exam-card" data-id="${e.id}">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <h3>${e.name}</h3>
                        <button class="btn btn-icon btn-delete-exam" data-id="${e.id}" style="background: #dc2626; color: white; padding: 4px 8px;">×</button>
                    </div>
                    <p class="exam-date">${e.date || '未设置日期'}</p>
                    ${status ? `<p class="exam-status" style="color: #f59e0b; font-size: 12px;">${status}</p>` : ''}
                    <div class="exam-stats">
                        <span>${e.question_count || 0} 题</span>
                        <span class="score">${e.user_score || 0} / ${e.total_score || 0} 分</span>
                    </div>
                </div>
            `}).join('');
            
            grid.querySelectorAll('.exam-card').forEach(card => {
                card.addEventListener('click', (e) => {
                    if (!e.target.classList.contains('btn-delete-exam')) {
                        const newExamId = parseInt(card.dataset.id);
                        
                        if (currentExamId !== newExamId) {
                            currentQuestions = [];
                            currentImage = null;
                            currentImageList = [];
                            currentImageIndex = 0;
                            selectedImagesForExtraction = [];
                        }
                        
                        currentExamId = newExamId;
                        showUploadModalForExam();
                    }
                });
            });
            
            grid.querySelectorAll('.btn-delete-exam').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const examId = parseInt(btn.dataset.id);
                    
                    if (confirm('确定要删除这个考试吗？')) {
                        const wasCurrentExam = currentExamId === examId;
                        
                        if (wasCurrentExam) {
                            currentExamId = null;
                            currentQuestions = [];
                            currentImage = null;
                            currentImageList = [];
                            currentImageIndex = 0;
                            selectedImagesForExtraction = [];
                            showPage('exams');
                        }
                        
                        delete processingExams[examId];
                        await apiRequest(`/exams/${examId}`, { method: 'DELETE' });
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
        
        if (exam.image_paths && exam.image_paths.length > 0) {
            currentImageList = exam.image_paths;
            currentImageIndex = 0;
            currentImage = currentImageList[currentImageIndex];
            loadImageToCanvas(currentImage);
        } else if (questions.length > 0 && questions[0].image_path) {
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
        updateImageNav();
        updateExtractButtonState();
        showPage('correction');
    } catch (error) {
        console.error('Failed to load correction workspace:', error);
    }
}

async function loadUploadedImagesForExam() {
    try {
        const exam = await apiRequest(`/exams/${currentExamId}`);
        const imagePaths = exam.image_paths || [];
        
        currentImageList = imagePaths;
        currentImageIndex = 0;
        if (imagePaths.length > 0) {
            currentImage = imagePaths[0];
        }
        
        const section = document.getElementById('uploaded-images-section');
        const list = document.getElementById('uploaded-images-list');
        
        if (imagePaths.length > 0) {
            section.style.display = 'block';
            let html = '';
            imagePaths.forEach((path, index) => {
                const fileName = path.split('/').pop();
                html += `
                    <div class="uploaded-image-item" data-path="${path}" data-index="${index}">
                        <img src="${path}" alt="试卷图片 ${index + 1}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23f0f0f0%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%2212%22>图片未找到</text></svg>'">
                        <button class="delete-btn" onclick="deleteImageFromExam('${path}')" title="删除">×</button>
                        <div class="image-name">${fileName}</div>
                    </div>
                `;
            });
            list.innerHTML = html;
            
            list.querySelectorAll('.uploaded-image-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    if (e.target.classList.contains('delete-btn')) return;
                    const path = item.dataset.path;
                    const idx = parseInt(item.dataset.index);
                    currentImage = path;
                    currentImageIndex = idx;
                    loadImageToCanvas(currentImage);
                });
            });
        } else {
            section.style.display = 'none';
        }
        
        return imagePaths;
    } catch (error) {
        console.error('加载已上传图片失败:', error);
        return [];
    }
}

async function deleteImageFromExam(imagePath) {
    if (!confirm('确定要删除这张图片吗？')) return;
    
    try {
        const response = await apiRequest(`/exams/${currentExamId}/images/${encodeURIComponent(imagePath)}`, {
            method: 'DELETE'
        });
        
        alert('图片已删除');
        await loadUploadedImagesForExam();
        
        if (currentImage === imagePath) {
            const remaining = response.remaining_images || [];
            if (remaining.length > 0) {
                currentImage = remaining[0];
                currentImageIndex = 0;
                loadImageToCanvas(currentImage);
            } else {
                currentImage = null;
                currentImageList = [];
                currentImageIndex = 0;
            }
        }
        
    } catch (error) {
        console.error('删除图片失败:', error);
        alert('删除失败: ' + error.message);
    }
}

function showExamActionsModal() {
    showModal('exam-actions');
}

function showUploadModalForExam() {
    updateExtractButtonState();
    showExamActionsModal();
}

function updateExtractButtonState() {
    const examId = currentExamId;
    const extractBtn = document.getElementById('extract-questions-btn');
    const cancelExtractBtn = document.getElementById('cancel-extract-btn');
    const gradeBtn = document.getElementById('start-grading-btn');
    const cancelGradingBtn = document.getElementById('cancel-grading-btn');
    
    if (!examId) {
        if (extractBtn) {
            extractBtn.disabled = false;
            extractBtn.textContent = '🔍 提取题目';
        }
        if (cancelExtractBtn) {
            cancelExtractBtn.style.display = 'none';
        }
        if (gradeBtn) {
            gradeBtn.disabled = true;
            gradeBtn.textContent = '📝 开始批改';
        }
        if (cancelGradingBtn) {
            cancelGradingBtn.style.display = 'none';
        }
        return;
    }
    
    const status = processingExams[examId] || {};
    
    if (extractBtn) {
        if (status.extracting) {
            extractBtn.disabled = true;
            extractBtn.textContent = '提取中...';
            if (cancelExtractBtn) cancelExtractBtn.style.display = 'inline-block';
        } else {
            extractBtn.disabled = false;
            extractBtn.textContent = '🔍 提取题目';
            if (cancelExtractBtn) cancelExtractBtn.style.display = 'none';
        }
    }
    
    if (gradeBtn) {
        if (status.grading) {
            gradeBtn.disabled = true;
            gradeBtn.textContent = '批改中...';
            if (cancelGradingBtn) cancelGradingBtn.style.display = 'inline-block';
        } else {
            gradeBtn.disabled = currentQuestions.length === 0;
            gradeBtn.textContent = '📝 开始批改';
            if (cancelGradingBtn) cancelGradingBtn.style.display = 'none';
        }
    }
}

function updateImageNav() {
    const nav = document.getElementById('image-nav');
    const counter = document.getElementById('image-counter');

    if (currentImageList.length > 1) {
        nav.style.display = 'flex';
        counter.textContent = `${currentImageIndex + 1} / ${currentImageList.length}`;
    } else {
        nav.style.display = 'none';
    }
}

function highlightQuestionForCurrentImage() {
    const currentImgPath = currentImage;
    const questionIndex = currentQuestions.findIndex(q => q.image_path === currentImgPath);
    if (questionIndex >= 0) {
        selectQuestion(questionIndex);
    }
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
    
    list.innerHTML = `
        <div class="questions-header" style="display: flex; align-items: center; margin-bottom: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
            <input type="checkbox" id="select-all-questions" style="margin-right: 10px;">
            <label for="select-all-questions" style="margin-right: 20px;">全选</label>
            <button id="batch-delete-btn" class="btn btn-danger" style="padding: 6px 12px; font-size: 14px; display: none;">批量删除</button>
        </div>
    ` + currentQuestions.map((q, index) => `
        <div class="question-item" data-index="${index}">
            <div class="question-header">
                <input type="checkbox" class="question-checkbox" data-index="${index}" style="margin-right: 10px;">
                <span class="question-index">第 </span>
                <input type="text" class="question-index-input"
                       value="${q.question_index || index + 1}"
                       data-field="question_index"
                       data-index="${index}"
                       style="width: 60px; padding: 4px 8px; border: 1px solid #e5e5e5; border-radius: 4px; font-size: 14px;"> 
                <span class="question-index"> 题</span>
                <div class="question-score">
                    <span class="score-tag">满分: ${q.max_score || 10}分</span>
                    <input type="number" class="max-score-input"
                           value="${q.max_score || 10}"
                           data-field="max_score"
                           data-index="${index}"
                           min="0" step="0.5"> 分
                    <button class="btn-delete-question ${processingExams[currentExamId]?.grading ? 'disabled' : ''}" 
                            data-index="${index}" 
                            title="${processingExams[currentExamId]?.grading ? '批改中无法删除' : '删除题目'}"
                            ${processingExams[currentExamId]?.grading ? 'disabled' : ''}>🗑️</button>
                </div>
            </div>
            <div class="question-text">${q.ocr_text ? marked.parse(q.ocr_text) : '未识别到题干'}</div>

            <div class="ocr-info">
                ${q.student_answer ? `
                <div class="ocr-field">
                    <span class="ocr-label">学生答案：</span>
                    <input type="text" class="ocr-input ocr-student-answer-input"
                           value="${q.student_answer || ''}"
                           data-field="student_answer"
                           data-index="${index}"
                           placeholder="请输入学生答案">
                </div>
                ` : ''}
                <div class="ocr-field">
                    <span class="ocr-label">知识点：</span>
                    <input type="text" class="ocr-input ocr-knowledge-input"
                           value="${q.knowledge_tags && q.knowledge_tags.length > 0 ? q.knowledge_tags.join(', ') : ''}"
                           data-field="knowledge_tags"
                           data-index="${index}"
                           placeholder="多个知识点用逗号分隔">
                </div>
            </div>

            <div class="standard-answer-section">
                <label class="answer-label">标准答案：</label>
                <textarea class="standard-answer-input" 
                          placeholder="点击开始批改后自动生成，也可手动输入..." 
                          data-field="standard_answer"
                          data-index="${index}">${q.standard_answer || ''}</textarea>
            </div>
            
            <div class="analysis-section">
                <label class="answer-label">解析：</label>
                <textarea class="analysis-input" 
                          placeholder="点击开始批改后自动生成，也可手动输入..." 
                          data-field="analysis"
                          data-index="${index}">${q.feedback || ''}</textarea>
            </div>
            
            ${q.user_score !== null ? `
                <div class="question-result">
                    <div class="score-display">
                        <span>得分：</span>
                        <input type="number" class="user-score-input"
                               value="${q.user_score}"
                               data-field="user_score"
                               data-index="${index}"
                               min="0" max="${q.max_score}" step="0.5"> 
                        <span> / ${q.max_score} 分</span>
                    </div>
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
    
    list.querySelectorAll('.question-index-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const value = e.target.value;
            
            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ question_index: value })
            });
            
            currentQuestions[index].question_index = value;
        });
        
        input.addEventListener('click', (e) => e.stopPropagation());
    });
    
    list.querySelectorAll('.user-score-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const value = parseFloat(e.target.value) || 0;
            
            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ user_score: value })
            });
            
            currentQuestions[index].user_score = value;
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
    
    list.querySelectorAll('.standard-answer-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const value = e.target.value;
            
            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ standard_answer: value })
            });
            
            currentQuestions[index].standard_answer = value;
        });
        
        input.addEventListener('click', (e) => e.stopPropagation());
    });
    
    list.querySelectorAll('.analysis-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const value = e.target.value;
            
            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ feedback: value })
            });
            
            currentQuestions[index].feedback = value;
        });
        
        input.addEventListener('click', (e) => e.stopPropagation());
    });

    list.querySelectorAll('.ocr-input').forEach(input => {
        input.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const field = e.target.dataset.field;
            const value = e.target.value;

            const updateData = {};
            if (field === 'knowledge_tags') {
                updateData.knowledge_tags = JSON.stringify(value.split(',').map(k => k.trim()).filter(k => k));
            } else if (field === 'difficulty') {
                updateData.difficulty = parseInt(value) || 3;
            } else {
                updateData[field] = value;
            }

            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify(updateData)
            });

            if (field === 'knowledge_tags') {
                currentQuestions[index].knowledge_tags = value.split(',').map(k => k.trim()).filter(k => k);
            } else if (field === 'difficulty') {
                currentQuestions[index].difficulty = parseInt(value) || 3;
            } else {
                currentQuestions[index][field] = value;
            }
        });

        input.addEventListener('click', (e) => e.stopPropagation());
    });

    list.querySelectorAll('.ocr-select').forEach(select => {
        select.addEventListener('change', async (e) => {
            const index = parseInt(e.target.dataset.index);
            const field = e.target.dataset.field;
            const value = parseInt(e.target.value);

            await apiRequest(`/questions/${currentQuestions[index].id}`, {
                method: 'PUT',
                body: JSON.stringify({ difficulty: value })
            });

            currentQuestions[index].difficulty = value;
        });

        select.addEventListener('click', (e) => e.stopPropagation());
    });
    
    list.querySelectorAll('.btn-delete-question').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const examId = currentExamId;
            if (processingExams[examId]?.grading) {
                alert('批改中无法删除题目，请等待批改完成');
                return;
            }
            
            const index = parseInt(btn.dataset.index);
            const question = currentQuestions[index];
            
            if (!confirm(`确定要删除第 ${question.question_index} 题吗？`)) {
                return;
            }
            
            try {
                await apiRequest(`/questions/${question.id}`, {
                    method: 'DELETE'
                });
                
                currentQuestions.splice(index, 1);
                renderQuestionsList();
                alert('题目已删除');
            } catch (error) {
                console.error('删除题目失败:', error);
                alert('删除题目失败: ' + error.message);
            }
        });
    });
    
    // 全选功能
    const selectAllCheckbox = document.getElementById('select-all-questions');
    const batchDeleteBtn = document.getElementById('batch-delete-btn');
    const checkboxes = list.querySelectorAll('.question-checkbox');
    
    selectAllCheckbox.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        checkboxes.forEach(checkbox => {
            checkbox.checked = isChecked;
        });
        updateBatchDeleteBtn();
    });
    
    // 单个复选框变化
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            updateSelectAllStatus();
            updateBatchDeleteBtn();
        });
        
        // 阻止复选框点击事件冒泡到题目项
        checkbox.addEventListener('click', (e) => e.stopPropagation());
    });
    
    // 批量删除按钮
    batchDeleteBtn.addEventListener('click', async () => {
        const examId = currentExamId;
        if (processingExams[examId]?.grading) {
            alert('批改中无法删除题目，请等待批改完成');
            return;
        }
        
        const selectedCheckboxes = list.querySelectorAll('.question-checkbox:checked');
        const selectedIndices = Array.from(selectedCheckboxes).map(cb => parseInt(cb.dataset.index));
        
        if (selectedIndices.length === 0) return;
        
        if (!confirm(`确定要删除选中的 ${selectedIndices.length} 道题目吗？`)) {
            return;
        }
        
        try {
            // 按索引从大到小删除，避免索引变化
            selectedIndices.sort((a, b) => b - a);
            
            for (const index of selectedIndices) {
                const question = currentQuestions[index];
                await apiRequest(`/questions/${question.id}`, {
                    method: 'DELETE'
                });
                currentQuestions.splice(index, 1);
            }
            
            renderQuestionsList();
            alert(`已删除 ${selectedIndices.length} 道题目`);
        } catch (error) {
            console.error('批量删除失败:', error);
            alert('批量删除失败: ' + error.message);
        }
    });
    
    function updateSelectAllStatus() {
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        selectAllCheckbox.checked = allChecked;
    }
    
    function updateBatchDeleteBtn() {
        const selectedCount = list.querySelectorAll('.question-checkbox:checked').length;
        batchDeleteBtn.style.display = selectedCount > 0 ? 'block' : 'none';
    }
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
        const subject = await apiRequest(`/subjects/${subjectId}`);
        
        renderTrendChart(data.exams);
        renderRateChart(data.exams);
        
        const subjectAnalysisSection = document.getElementById('subject-analysis-section');
        const subjectAnalysisContent = document.getElementById('subject-analysis-content');
        
        if (subject.analysis_report) {
            let reportText = '';
            try {
                if (typeof subject.analysis_report === 'string') {
                    try {
                        const parsed = JSON.parse(subject.analysis_report);
                        reportText = parsed.analysis_report || parsed.summary || subject.analysis_report;
                    } catch (e) {
                        reportText = subject.analysis_report;
                    }
                } else {
                    reportText = subject.analysis_report.analysis_report || subject.analysis_report.summary || JSON.stringify(subject.analysis_report);
                }
            } catch (e) {
                reportText = subject.analysis_report || '暂无分析报告';
            }
            
            const processedText = reportText.replace(/\\n/g, '\n');
            subjectAnalysisContent.innerHTML = `<div class="subject-report-text">${marked.parse(processedText)}</div>`;
            subjectAnalysisSection.style.display = 'block';
        } else {
            subjectAnalysisSection.style.display = 'none';
        }
        
        const analysis = document.getElementById('exam-analysis');
        if (data.exams.length === 0) {
            analysis.innerHTML = '<p>暂无考试数据</p>';
        } else {
            renderExamAnalysis(data.exams);
        }
    } catch (error) {
        console.error('Failed to load dashboard data:', error);
    }
}

function renderExamAnalysis(exams) {
    const container = document.getElementById('exam-analysis');
    let html = '<h2>考试分析报告</h2>';
    
    exams.forEach(exam => {
        let reportData = null;
        let reportText = '';
        if (exam.analysis_report) {
            try {
                if (typeof exam.analysis_report === 'string') {
                    try {
                        const parsed = JSON.parse(exam.analysis_report);
                        reportData = parsed;
                        reportText = parsed.summary || parsed.analysis_report || exam.analysis_report;
                    } catch (e) {
                        reportText = exam.analysis_report;
                        reportData = { summary: exam.analysis_report };
                    }
                } else {
                    reportData = exam.analysis_report;
                    reportText = exam.analysis_report.summary || exam.analysis_report.analysis_report || JSON.stringify(exam.analysis_report);
                }
            } catch (e) {
                reportText = exam.analysis_report;
                reportData = { summary: exam.analysis_report };
            }
        }
        
        const hasReport = reportData && (reportData.summary || reportData.exam_name);
        
        html += `
            <div class="exam-report-card" data-exam-id="${exam.id}">
                <div class="exam-report-header">
                    <h3>${exam.name}</h3>
                    <span class="exam-date">${exam.date}</span>
                </div>
                ${hasReport ? `
                    <div class="exam-report-content">
                        <div class="score-summary">
                            <span class="score-item">总分: <strong>${reportData.total_score || exam.total_score}</strong></span>
                            <span class="score-item">得分: <strong>${reportData.total_earned_score || exam.user_score}</strong></span>
                            <span class="score-item">得分率: <strong>${reportData.score_analysis?.score_rate || exam.score_rate + '%'}</strong></span>
                        </div>
                        <div class="summary-text">
                            <h4>分析总结:</h4>
                            <div>${marked.parse((reportText || '暂无总结').replace(/\\n/g, '\n'))}</div>
                        </div>
                        <div class="report-actions">
                            <button class="btn btn-sm btn-primary" onclick="editAnalysisReport(${exam.id})">编辑报告</button>
                            <button class="btn btn-sm btn-secondary" onclick="viewFullReport(${exam.id})">查看详情</button>
                        </div>
                    </div>
                ` : `
                    <div class="no-report">
                        <p>暂无分析报告</p>
                        <button class="btn btn-sm btn-success" onclick="generateAnalysisForExam(${exam.id})">生成分析报告</button>
                    </div>
                `}
            </div>
        `;
    });
    
    container.innerHTML = html;
}

async function generateAnalysisForExam(examId, event) {
    if (!confirm('确定要生成分析报告吗？请确保已完成所有题目的批改。')) return;
    
    if (processingExams[examId]?.analyzing) {
        alert('当前考试正在分析中，请稍候再试');
        return;
    }
    
    const btn = event?.target;
    if (btn) {
        btn.disabled = true;
        btn.textContent = '生成中...';
    }
    
    processingExams[examId] = { ...processingExams[examId], analyzing: true };
    updateExamCardStatus(examId);
    
    try {
        const response = await apiRequest(`/analyze-exam/${examId}`, {
            method: 'POST'
        });
        
        alert('分析报告生成成功！\n\n' +
            `考试名称: ${response.exam_name || '未命名'}\n` +
            `总分: ${response.total_score}\n` +
            `得分: ${response.total_earned_score}\n` +
            `得分率: ${response.score_analysis?.score_rate || '0%'}`);
        
        loadDashboardData(currentSubjectId);
    } catch (error) {
        console.error('生成分析报告失败:', error);
        alert('生成分析报告失败: ' + error.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '生成分析报告';
        }
        if (processingExams[examId]) {
            processingExams[examId].analyzing = false;
        }
        updateExamCardStatus(examId);
    }
}

async function generateAnalysisForSubject(subjectId) {
    if (!confirm('确定要生成学科分析报告吗？请确保该学科下已有考试数据。')) return;
    
    if (processingSubjects[subjectId]) {
        alert('该学科正在分析中，请稍候再试');
        return;
    }
    
    const subject = await apiRequest(`/subjects/${subjectId}`);
    if (!subject.exam_count || subject.exam_count === 0) {
        alert('该学科下没有考试数据，无法生成分析报告。');
        return;
    }
    
    processingSubjects[subjectId] = true;
    updateSubjectCardStatus(subjectId);
    
    try {
        await apiRequest(`/analyze-subject/${subjectId}`, {
            method: 'POST'
        });
        
        alert('学科分析完成！\n\n请前往"分析仪表盘"查看详细报告');
        
        loadSubjects();
    } catch (error) {
        console.error('生成学科分析报告失败:', error);
        alert('生成学科分析报告失败: ' + error.message);
    } finally {
        processingSubjects[subjectId] = false;
        updateSubjectCardStatus(subjectId);
    }
}

function updateSubjectCardStatus(subjectId) {
    const cards = document.querySelectorAll(`.subject-card[data-id="${subjectId}"]`);
    cards.forEach(card => {
        const analyzeBtn = card.querySelector('.btn-analyze-subject');
        if (analyzeBtn) {
            if (processingSubjects[subjectId]) {
                analyzeBtn.disabled = true;
                analyzeBtn.textContent = '分析中...';
            } else {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = '生成学科分析';
            }
        }
    });
}

async function editAnalysisReport(examId) {
    try {
        const exam = await apiRequest(`/exams/${examId}`);
        let reportData = null;
        let summaryText = '';
        
        if (exam.analysis_report) {
            try {
                if (typeof exam.analysis_report === 'string') {
                    try {
                        const parsed = JSON.parse(exam.analysis_report);
                        reportData = parsed;
                        summaryText = parsed.summary || parsed.analysis_report || '';
                    } catch (e) {
                        summaryText = exam.analysis_report;
                        reportData = { summary: exam.analysis_report };
                    }
                } else {
                    reportData = exam.analysis_report;
                    summaryText = exam.analysis_report.summary || exam.analysis_report.analysis_report || '';
                }
            } catch (e) {
                summaryText = exam.analysis_report;
                reportData = { summary: exam.analysis_report };
            }
        }
        
        const modalContent = `
            <div class="form-group">
                <label>考试名称</label>
                <input type="text" id="edit-exam-name" class="form-input" value="${reportData?.exam_name || exam.name || ''}">
            </div>
            <div class="form-group">
                <label>总分</label>
                <input type="number" id="edit-total-score" class="form-input" value="${reportData?.total_score || exam.total_score || 0}">
            </div>
            <div class="form-group">
                <label>得分</label>
                <input type="number" id="edit-earned-score" class="form-input" value="${reportData?.total_earned_score || exam.user_score || 0}">
            </div>
            <div class="form-group">
                <label>分析总结</label>
                <textarea id="edit-summary" class="form-textarea" rows="8">${summaryText.replace(/\\n/g, '\n')}</textarea>
            </div>
        `;
        
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.id = 'edit-report-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>编辑分析报告</h2>
                    <span class="close" onclick="closeEditModal()">&times;</span>
                </div>
                <div class="modal-body">
                    ${modalContent}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeEditModal()">取消</button>
                    <button class="btn btn-primary" onclick="saveAnalysisReport(${examId})">保存</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
    } catch (error) {
        console.error('加载考试数据失败:', error);
        alert('加载失败: ' + error.message);
    }
}

function closeEditModal() {
    const modal = document.getElementById('edit-report-modal');
    if (modal) {
        modal.remove();
    }
}

async function saveAnalysisReport(examId) {
    const examName = document.getElementById('edit-exam-name').value;
    const totalScore = parseFloat(document.getElementById('edit-total-score').value) || 0;
    const earnedScore = parseFloat(document.getElementById('edit-earned-score').value) || 0;
    const summary = document.getElementById('edit-summary').value;
    
    const reportData = {
        exam_name: examName,
        total_score: totalScore,
        total_earned_score: earnedScore,
        summary: summary,
        score_analysis: {
            total_score: totalScore,
            total_earned_score: earnedScore,
            score_rate: totalScore > 0 ? (earnedScore / totalScore * 100).toFixed(1) + '%' : '0%'
        }
    };
    
    try {
        await apiRequest(`/exams/${examId}`, {
            method: 'PUT',
            body: JSON.stringify({ analysis_report: JSON.stringify(reportData) })
        });
        
        alert('报告保存成功！');
        closeEditModal();
        loadDashboardData(currentSubjectId);
    } catch (error) {
        console.error('保存失败:', error);
        alert('保存失败: ' + error.message);
    }
}

function viewFullReport(examId) {
    window.location.href = `?page=correction&examId=${examId}`;
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
        // 过滤掉metadata记录
        const filteredPrompts = prompts.filter(p => p.name !== 'metadata');
        const list = document.getElementById('prompts-list');
        
        list.innerHTML = `
            <h3>可用 Prompts</h3>
            ${filteredPrompts.map(p => `
                <div class="prompt-item" data-id="${p.id}" data-name="${p.name}">
                    <h4>${p.role || p.name}</h4>
                    <p>${p.description}</p>
                </div>
            `).join('')}
        `;
        
        list.querySelectorAll('.prompt-item').forEach(item => {
            item.addEventListener('click', () => {
                const prompt = filteredPrompts.find(p => p.id === parseInt(item.dataset.id));
                showPromptEditor(prompt);
            });
        });
        
        if (filteredPrompts.length > 0) {
            showPromptEditor(filteredPrompts[0]);
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
        document.getElementById('vision-api-key').value = settings.vision_api_key || '';
        document.getElementById('vision-api-base').value = settings.vision_api_base || '';
        document.getElementById('grading-api-key').value = settings.grading_api_key || '';
        document.getElementById('grading-api-base').value = settings.grading_api_base || '';
        document.getElementById('analysis-api-key').value = settings.analysis_api_key || '';
        document.getElementById('analysis-api-base').value = settings.analysis_api_base || '';
        document.getElementById('subject-analysis-api-key').value = settings.subject_analysis_api_key || '';
        document.getElementById('subject-analysis-api-base').value = settings.subject_analysis_api_base || '';
        document.getElementById('model-general').value = settings.model_general || '';
        document.getElementById('model-vision').value = settings.model_vision || '';
        document.getElementById('model-grading').value = settings.model_grading || '';
        document.getElementById('model-analysis').value = settings.model_analysis || '';
        document.getElementById('model-subject-analysis').value = settings.model_subject_analysis || '';
        document.getElementById('vision-deep-thinking').checked = settings.vision_deep_thinking === 'true' || settings.vision_deep_thinking === true;
        document.getElementById('grading-deep-thinking').checked = settings.grading_deep_thinking === 'true' || settings.grading_deep_thinking === true;
        document.getElementById('analysis-deep-thinking').checked = settings.analysis_deep_thinking === 'true' || settings.analysis_deep_thinking === true;
        document.getElementById('subject-analysis-deep-thinking').checked = settings.subject_analysis_deep_thinking === 'true' || settings.subject_analysis_deep_thinking === true;
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

async function saveSettings() {
    const settings = {
        api_key: document.getElementById('api-key').value,
        api_base: document.getElementById('api-base').value,
        vision_api_key: document.getElementById('vision-api-key').value,
        vision_api_base: document.getElementById('vision-api-base').value,
        grading_api_key: document.getElementById('grading-api-key').value,
        grading_api_base: document.getElementById('grading-api-base').value,
        analysis_api_key: document.getElementById('analysis-api-key').value,
        analysis_api_base: document.getElementById('analysis-api-base').value,
        subject_analysis_api_key: document.getElementById('subject-analysis-api-key').value,
        subject_analysis_api_base: document.getElementById('subject-analysis-api-base').value,
        model_general: document.getElementById('model-general').value,
        model_vision: document.getElementById('model-vision').value,
        model_grading: document.getElementById('model-grading').value,
        model_analysis: document.getElementById('model-analysis').value,
        model_subject_analysis: document.getElementById('model-subject-analysis').value,
        vision_deep_thinking: document.getElementById('vision-deep-thinking').checked ? 'true' : 'false',
        grading_deep_thinking: document.getElementById('grading-deep-thinking').checked ? 'true' : 'false',
        analysis_deep_thinking: document.getElementById('analysis-deep-thinking').checked ? 'true' : 'false',
        subject_analysis_deep_thinking: document.getElementById('subject-analysis-deep-thinking').checked ? 'true' : 'false'
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

async function testApiConnection(type) {
    const configMap = {
        'general': {
            apiKey: 'api-key',
            apiBase: 'api-base',
            model: 'model-general'
        },
        'vision': {
            apiKey: 'vision-api-key',
            apiBase: 'vision-api-base',
            model: 'model-vision'
        },
        'grading': {
            apiKey: 'grading-api-key',
            apiBase: 'grading-api-base',
            model: 'model-grading'
        },
        'analysis': {
            apiKey: 'analysis-api-key',
            apiBase: 'analysis-api-base',
            model: 'model-analysis'
        },
        'subject-analysis': {
            apiKey: 'subject-analysis-api-key',
            apiBase: 'subject-analysis-api-base',
            model: 'model-subject-analysis'
        }
    };
    
    const config = configMap[type];
    if (!config) {
        alert('未知的配置类型');
        return;
    }
    
    const apiKey = document.getElementById(config.apiKey).value;
    const apiBase = document.getElementById(config.apiBase).value;
    const model = document.getElementById(config.model).value;
    
    if (!apiKey || !apiBase || !model) {
        alert('请填写完整的API密钥、API地址和模型名称');
        return;
    }
    
    const btn = event.target;
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '测试中...';
    
    try {
        const response = await apiRequest('/settings/test', {
            method: 'POST',
            body: JSON.stringify({
                api_key: apiKey,
                api_base: apiBase,
                model: model
            })
        });
        
        if (response.success) {
            alert('✓ ' + response.message);
        } else {
            alert('✗ ' + response.message);
        }
    } catch (error) {
        console.error('测试连接失败:', error);
        alert('✗ 测试失败: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const examIdParam = urlParams.get('examId');
    const pageParam = urlParams.get('page');
    
    if (examIdParam) {
        currentExamId = parseInt(examIdParam);
        if (currentExamId) {
            loadExam(currentExamId);
        }
    }
    
    if (pageParam === 'correction' && currentExamId) {
        loadCorrectionWorkspace();
    }
    
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
        
        try {
            await apiRequest('/subjects', {
                method: 'POST',
                body: JSON.stringify({ name })
            });
            
            hideModal('subject');
            loadSubjects();
        } catch (error) {
            console.error('创建学科失败:', error);
            alert('创建学科失败: ' + error.message);
        }
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
        
        try {
            const newExam = await apiRequest('/exams', {
                method: 'POST',
                body: JSON.stringify({
                    subject_id: currentSubjectId,
                    name,
                    date
                })
            });
            
            hideModal('exam');
            
            currentExamId = newExam.id;
            currentQuestions = [];
            currentImage = null;
            currentImageList = [];
            currentImageIndex = 0;
            selectedImagesForExtraction = [];
            
            loadExams(currentSubjectId);
            showUploadModalForExam();
        } catch (error) {
            console.error('创建考试失败:', error);
            alert('创建考试失败: ' + error.message);
        }
    });
    
    document.getElementById('cancel-exam-btn').addEventListener('click', () => hideModal('exam'));
    
    document.getElementById('back-to-exams').addEventListener('click', () => {
        showPage('exams');
    });
    
    document.getElementById('upload-btn').addEventListener('click', async () => {
        await loadUploadedImagesForExam();
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

        currentImageList = [];

        try {
            for (let i = 0; i < totalFiles; i++) {
                const file = filesArray[i];
                const formData = new FormData();
                formData.append('file', file);
                formData.append('exam_id', currentExamId);
                formData.append('extract', 'false');

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

                if (result.image_path) {
                    currentImageList.push(result.image_path);
                }

                uploadedCount++;
                const progress = (uploadedCount / totalFiles) * 100;
                document.querySelector('.progress-fill').style.width = `${progress}%`;
            }

            if (currentImageList.length > 0) {
                currentImageIndex = 0;
                currentImage = currentImageList[currentImageIndex];

                updateImageNav();

                currentQuestions = [];
                loadCorrectionWorkspace();
                hideModal('upload');
            }
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
        if (currentImageList.length === 0) {
            alert('请先上传试卷图片');
            return;
        }

        showSelectImagesModal();
    }

    let selectedImagesForExtraction = [];
    
    function showSelectImagesModal() {
        const modal = document.getElementById('select-images-modal');
        const list = document.getElementById('select-images-list');
        
        selectedImagesForExtraction = [...currentImageList];
        
        renderSelectImagesList();
        showModal('select-images');
    }
    
    function renderSelectImagesList() {
        const list = document.getElementById('select-images-list');
        
        list.innerHTML = currentImageList.map((path, index) => {
            const isSelected = selectedImagesForExtraction.includes(path);
            return `
                <div class="select-image-item ${isSelected ? 'selected' : ''}" data-path="${path}" data-index="${index}">
                    <img src="${path}" alt="图片 ${index + 1}">
                    ${isSelected ? '<div class="check-icon">✓</div>' : ''}
                    <div class="image-number">图片 ${index + 1}</div>
                </div>
            `;
        }).join('');
        
        list.querySelectorAll('.select-image-item').forEach(item => {
            item.addEventListener('click', () => {
                const path = item.dataset.path;
                
                if (selectedImagesForExtraction.includes(path)) {
                    selectedImagesForExtraction = selectedImagesForExtraction.filter(p => p !== path);
                } else {
                    selectedImagesForExtraction.push(path);
                    selectedImagesForExtraction.sort((a, b) => {
                        return currentImageList.indexOf(a) - currentImageList.indexOf(b);
                    });
                }
                
                renderSelectImagesList();
            });
        });
    }
    
    async function confirmExtractImages() {
        if (selectedImagesForExtraction.length === 0) {
            alert('请至少选择一张图片');
            return;
        }
        
        const examId = currentExamId;
        if (!examId) {
            alert('请先选择一个考试');
            return;
        }
        
        if (processingExams[examId]?.extracting) {
            alert('该考试正在提取题目中，请稍候再试');
            return;
        }
        
        hideModal('select-images');
        
        cancelExtractRequest = false;
        
        const btn = document.getElementById('extract-questions-btn');
        btn.disabled = true;
        btn.textContent = '提取中...';
        
        processingExams[examId] = { ...processingExams[examId], extracting: true };
        updateExamCardStatus(examId);
        updateExtractButtonState();

        try {
            console.log('开始提取题目，图片列表:', selectedImagesForExtraction);

            const formData = new FormData();
            formData.append('exam_id', examId);
            formData.append('extract', 'true');

            for (let i = 0; i < selectedImagesForExtraction.length; i++) {
                formData.append('image_paths', selectedImagesForExtraction[i]);
            }

            const requestUrl = `${API_BASE}/extract-questions-batch`;
            console.log('发送请求到:', requestUrl);

            const response = await fetch(requestUrl, {
                method: 'POST',
                body: formData
            });

            if (cancelExtractRequest) {
                console.log('提取已取消');
                return;
            }

            console.log('提取题目响应状态:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('HTTP错误响应:', errorText);
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
            }

            const result = await response.json();
            console.log('提取题目响应结果:', result);

            if (result.error) {
                alert('分析失败：' + result.error);
                return;
            }

            if (result.questions && result.questions.length > 0) {
                console.log('提取到的题目数量:', result.questions.length);
                currentQuestions = result.questions;
                renderQuestionsList();
                alert('题目提取完成！共提取到 ' + result.questions.length + ' 道题目');
            } else {
                alert('未检测到题目，请检查图片是否清晰');
            }
        } catch (error) {
            if (cancelExtractRequest) {
                console.log('提取已取消');
                return;
            }
            console.error('提取题目失败:', error);
            console.error('错误详情:', error.stack);
            alert('分析失败：' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '提取题目';
            if (processingExams[examId]) {
                processingExams[examId].extracting = false;
            }
            updateExamCardStatus(examId);
            updateExtractButtonState();
        }
    }
    
    document.getElementById('cancel-upload-btn').addEventListener('click', () => {
        hideModal('upload');
        document.getElementById('upload-area').style.display = 'block';
        document.getElementById('upload-progress').style.display = 'none';
    });
    
    document.getElementById('cancel-select-images-btn').addEventListener('click', () => {
        hideModal('select-images');
    });
    
    document.getElementById('confirm-select-images-btn').addEventListener('click', confirmExtractImages);
    
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

    document.getElementById('prev-image-btn').addEventListener('click', () => {
        if (currentImageIndex > 0) {
            currentImageIndex--;
            currentImage = currentImageList[currentImageIndex];
            updateImageNav();
            loadImageToCanvas(currentImage);
            highlightQuestionForCurrentImage();
        }
    });

    document.getElementById('next-image-btn').addEventListener('click', () => {
        if (currentImageIndex < currentImageList.length - 1) {
            currentImageIndex++;
            currentImage = currentImageList[currentImageIndex];
            updateImageNav();
            loadImageToCanvas(currentImage);
            highlightQuestionForCurrentImage();
        }
    });

    document.getElementById('add-question-btn').addEventListener('click', () => {
        showModal('add-question');
    });
    
    document.getElementById('cancel-add-question-btn').addEventListener('click', () => {
        hideModal('add-question');
    });
    
    document.getElementById('add-question-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const questionData = {
            question_index: document.getElementById('new-question-index').value,
            ocr_text: document.getElementById('new-question-text').value,
            max_score: parseInt(document.getElementById('new-question-score').value) || 5,
            standard_answer: document.getElementById('new-question-answer').value,
            difficulty: document.getElementById('new-question-difficulty').value
        };
        
        try {
            const newQuestion = await apiRequest(`/exams/${currentExamId}/questions`, {
                method: 'POST',
                body: JSON.stringify(questionData)
            });
            
            currentQuestions.push(newQuestion);
            renderQuestionsList();
            hideModal('add-question');
            document.getElementById('add-question-form').reset();
            alert('题目添加成功！');
        } catch (error) {
            console.error('添加题目失败:', error);
            alert('添加题目失败: ' + error.message);
        }
    });
    
    document.getElementById('start-grading-btn').addEventListener('click', async () => {
        if (currentQuestions.length === 0) {
            alert('请先上传试卷');
            return;
        }
        
        const examId = currentExamId;
        if (!examId) {
            alert('请先选择一个考试');
            return;
        }
        
        if (processingExams[examId]?.grading) {
            alert('该考试正在批改中，请稍候再试');
            return;
        }
        
        cancelGradingRequest = false;
        
        const btn = document.getElementById('start-grading-btn');
        btn.disabled = true;
        btn.textContent = '批改中...';
        
        processingExams[examId] = { ...processingExams[examId], grading: true };
        updateExamCardStatus(examId);
        updateExtractButtonState();
        
        try {
            console.log('开始批改，请求URL:', `${API_BASE}/grade-all/${examId}`);
            const gradedQuestions = await apiRequest(`/grade-all/${examId}`, {
                method: 'POST'
            });
            
            if (cancelGradingRequest) {
                console.log('批改已取消');
                return;
            }
            
            console.log('批改完成，返回结果:', gradedQuestions);
            currentQuestions = gradedQuestions;
            renderQuestionsList();
            
            alert('批改完成！');
        } catch (error) {
            if (cancelGradingRequest) {
                console.log('批改已取消');
                return;
            }
            console.error('批改失败:', error);
            alert('批改失败：' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '开始批改';
            if (processingExams[examId]) {
                processingExams[examId].grading = false;
            }
            updateExamCardStatus(examId);
            updateExtractButtonState();
        }
    });

    document.getElementById('generate-analysis-btn').addEventListener('click', async () => {
        if (currentQuestions.length === 0) {
            alert('请先上传试卷');
            return;
        }

        const hasScores = currentQuestions.some(q => q.user_score !== null && q.user_score !== undefined);
        if (!hasScores) {
            alert('请先完成批改再生成分析报告');
            return;
        }

        const btn = document.getElementById('generate-analysis-btn');
        btn.disabled = true;
        btn.textContent = '分析中...';

        try {
            const examId = currentExamId;
            const response = await apiRequest(`/analyze-exam/${examId}`, {
                method: 'POST'
            });

            alert('分析报告生成成功！\n\n' +
                `考试名称: ${response.exam_name || '未命名'}\n` +
                `总分: ${response.total_score}\n` +
                `得分: ${response.total_earned_score}\n` +
                `得分率: ${response.score_analysis?.score_rate || '0%'}\n\n` +
                `查看详细报告请前往"分析仪表盘"页面`);

            loadExam(examId);
        } catch (error) {
            console.error('生成分析报告失败:', error);
            alert('生成分析报告失败: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '📊 生成分析报告';
        }
    });

    document.getElementById('save-prompt-btn').addEventListener('click', savePrompt);
    document.getElementById('reset-prompt-btn').addEventListener('click', resetPrompt);
    
    document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
    document.getElementById('reset-settings-btn').addEventListener('click', resetSettings);
    
    document.getElementById('cancel-extract-btn').addEventListener('click', () => {
        if (confirm('确定要取消提取吗？')) {
            cancelExtractRequest = true;
            const examId = currentExamId;
            if (processingExams[examId]) {
                processingExams[examId].extracting = false;
            }
            updateExamCardStatus(examId);
            updateExtractButtonState();
        }
    });
    
    document.getElementById('cancel-grading-btn').addEventListener('click', () => {
        if (confirm('确定要终止批改吗？当前已批改的题目将保留。')) {
            cancelGradingRequest = true;
            const examId = currentExamId;
            if (processingExams[examId]) {
                processingExams[examId].grading = false;
            }
            updateExamCardStatus(examId);
            updateExtractButtonState();
        }
    });
    
    document.getElementById('dashboard-subject-select').addEventListener('change', (e) => {
        loadDashboardData(parseInt(e.target.value));
    });
    
    loadSubjects();
});
