const API_URL = '/chat';
let currentThreadId = 'demo-thread';

// Generate new thread ID
function generateNewThread() {
    currentThreadId = 'thread-' + Date.now();
    document.getElementById('thread-id').textContent = currentThreadId;
    clearChat();
}

// Clear chat
function clearChat() {
    const messagesContainer = document.getElementById('chat-messages');
    messagesContainer.innerHTML = `
        <div class="welcome-message">
                <div class="message message-assistant">
                <div class="message-label">
                    <img src="/static/icons8-бот-96.png" alt="Assistant" style="width: 48px; height: 48px; object-fit: contain;">
                </div>
                <div class="message-content">
                    New conversation started. Ask a question!
                    <div class="examples-section">
                        <p class="examples-label">Try asking:</p>
                        <div class="example-chips">
                            <button class="example-chip" onclick="insertExample('User signed up with Google. How can they change their password?')">User signed up with Google. How can they change their password?</button>
                            <button class="example-chip" onclick="insertExample('What to do if payment failed?')">What to do if payment failed?</button>
                            <button class="example-chip" onclick="insertExample('How to enable two-factor authentication?')">How to enable two-factor authentication?</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Insert example into input
function insertExample(text) {
    const input = document.getElementById('message-input');
    input.value = text;
    input.focus();
    // Auto-resize
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
}

// Copy Thread ID
function copyThreadId(event) {
    const threadId = document.getElementById('thread-id').textContent;
    navigator.clipboard.writeText(threadId).then(() => {
        const btn = event.target.closest('.btn-copy');
        if (btn) {
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
            setTimeout(() => {
                btn.innerHTML = originalHTML;
            }, 1000);
        }
    });
}

// Проверяет, нужно ли показывать кнопку создания тикета
function shouldShowCreateTicketButton(answerText, metadata) {
    // Если тикет уже создан, не показываем кнопку
    if (metadata.ticket) {
        return false;
    }
    
    // Проверяем текст ответа на предложение создать тикет
    const ticketKeywords = [
        'create a ticket',
        'create ticket',
        'create a support ticket',
        'open a ticket',
        'file a ticket',
        'submit a ticket',
        'создать тикет',
        'создайте тикет',
        'открыть тикет'
    ];
    
    const answerLower = answerText.toLowerCase();
    return ticketKeywords.some(keyword => answerLower.includes(keyword));
}

// Создает тикет из сообщения
async function createTicketFromMessage(answerText, userMessage, button) {
    const originalText = button.textContent;
    
    // Отключаем кнопку и показываем загрузку
    button.disabled = true;
    button.textContent = '⏳ Creating ticket...';
    
    try {
        // Определяем приоритет на основе контекста
        let priority = 'P2';
        const answerLower = answerText.toLowerCase();
        if (answerLower.includes('repeated') || answerLower.includes('still') || answerLower.includes('again')) {
            priority = 'P1';
        }
        
        const response = await fetch(CREATE_TICKET_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                title: userMessage.substring(0, 100),
                description: `User question: ${userMessage}\n\nAgent response: ${answerText}`,
                priority: priority,
                thread_id: currentThreadId
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Обновляем сообщение с информацией о созданном тикете
        if (data.ticket_id) {
            button.textContent = `✅ Ticket Created: ${data.ticket_id}`;
            button.style.background = '#d4edda';
            button.style.color = '#155724';
            button.style.cursor = 'default';
            
            // Добавляем информацию о тикете в метаданные сообщения
            const messageDiv = button.closest('.message');
            if (messageDiv) {
                const metaDiv = messageDiv.querySelector('.message-meta');
                if (metaDiv) {
                    const ticketDiv = document.createElement('div');
                    ticketDiv.className = 'message-action ticket';
                    ticketDiv.style.marginTop = '10px';
                    ticketDiv.innerHTML = `✅ Created ticket: <span class="ticket-id" onclick="copyToClipboard('${data.ticket_id}')">${data.ticket_id}</span> (Priority: ${data.priority || priority})`;
                    metaDiv.appendChild(ticketDiv);
                }
            }
        }
    } catch (error) {
        console.error('Error creating ticket:', error);
        button.textContent = '❌ Failed to create ticket';
        button.style.background = '#f8d7da';
        button.style.color = '#721c24';
        
        setTimeout(() => {
            button.disabled = false;
            button.textContent = originalText;
            button.style.background = '';
            button.style.color = '';
        }, 3000);
    }
}

// Add message to chat
function addMessage(content, isUser = false, metadata = {}, userMessage = '') {
    // Сохраняем userMessage для использования в кнопке создания тикета
    if (userMessage) {
        lastUserMessage = userMessage;
    }
    const messagesContainer = document.getElementById('chat-messages');
    
    // Remove welcome message if exists
    const welcomeMsg = messagesContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    // Remove typing indicator if exists
    const typingIndicator = messagesContainer.querySelector('.typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'message-user' : 'message-assistant'}`;
    
    const label = document.createElement('div');
    label.className = 'message-label';
    if (isUser) {
        const userIcon = document.createElement('img');
        userIcon.src = '/static/icons8-circled-male-user-skin-type-3-96.png';
        userIcon.alt = 'You';
        userIcon.style.width = '48px';
        userIcon.style.height = '48px';
        userIcon.style.objectFit = 'contain';
        userIcon.style.display = 'block';
        userIcon.onerror = function() {
            console.error('Failed to load user icon:', userIcon.src);
            label.textContent = 'You';
        };
        label.appendChild(userIcon);
    } else {
        const icon = document.createElement('img');
        icon.src = '/static/icons8-бот-96.png';
        icon.alt = 'Assistant';
        icon.style.width = '48px';
        icon.style.height = '48px';
        icon.style.objectFit = 'contain';
        label.appendChild(icon);
    }
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    // Add metadata (sources, actions, next_steps) for assistant messages
    if (!isUser && (metadata.sources || metadata.actions_taken || metadata.next_steps || metadata.ticket)) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        
        // Sources
        if (metadata.sources && metadata.sources.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'message-sources';
            const sourcesTitle = document.createElement('div');
            sourcesTitle.className = 'message-sources-title';
            sourcesTitle.textContent = 'Sources:';
            sourcesDiv.appendChild(sourcesTitle);
            
            metadata.sources.forEach(source => {
                const link = document.createElement('a');
                link.href = source.url || source;
                link.target = '_blank';
                link.className = `message-source-link relevance-${source.relevance || 'medium'}`;
                // Показываем title и URL
                const title = source.title || source.url || source;
                const url = source.url || '';
                link.textContent = url ? `${title} — ${url}` : title;
                link.title = url || title;
                sourcesDiv.appendChild(link);
            });
            
            metaDiv.appendChild(sourcesDiv);
        }
        
        // Actions taken (badges)
        if (metadata.actions_taken && metadata.actions_taken.length > 0) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            actionsDiv.style.marginTop = '10px';
            actionsDiv.style.display = 'flex';
            actionsDiv.style.gap = '8px';
            actionsDiv.style.flexWrap = 'wrap';
            
            metadata.actions_taken.forEach(action => {
                const badge = document.createElement('span');
                badge.className = 'action-badge';
                badge.style.padding = '4px 10px';
                badge.style.borderRadius = '12px';
                badge.style.fontSize = '0.8em';
                badge.style.fontWeight = '600';
                
                if (action === 'search_kb') {
                    badge.textContent = '🔍 KB Search';
                    badge.style.background = '#e3f2fd';
                    badge.style.color = '#1976d2';
                } else if (action === 'create_ticket') {
                    badge.textContent = '🎫 Ticket Created';
                    badge.style.background = '#fff3e0';
                    badge.style.color = '#f57c00';
                }
                
                actionsDiv.appendChild(badge);
            });
            
            metaDiv.appendChild(actionsDiv);
        }
        
        // Ticket info
        if (metadata.ticket) {
            const ticketDiv = document.createElement('div');
            ticketDiv.className = 'message-action ticket';
            ticketDiv.innerHTML = `✅ Created ticket: <span class="ticket-id" onclick="copyToClipboard('${metadata.ticket.ticket_id}')">${metadata.ticket.ticket_id}</span> (Priority: ${metadata.ticket.priority})`;
            metaDiv.appendChild(ticketDiv);
        }
        
        // Next steps
        if (metadata.next_steps && metadata.next_steps.length > 0) {
            const stepsDiv = document.createElement('div');
            stepsDiv.className = 'message-next-steps';
            stepsDiv.style.marginTop = '12px';
            stepsDiv.style.paddingTop = '12px';
            stepsDiv.style.borderTop = '1px solid rgba(0,0,0,0.08)';
            
            const stepsTitle = document.createElement('div');
            stepsTitle.className = 'message-sources-title';
            stepsTitle.textContent = '📋 Next steps:';
            stepsTitle.style.marginBottom = '8px';
            stepsTitle.style.color = '#ffffff';
            stepsDiv.appendChild(stepsTitle);
            
            const stepsList = document.createElement('ul');
            stepsList.style.margin = '0';
            stepsList.style.paddingLeft = '20px';
            stepsList.style.listStyle = 'none';
            
            metadata.next_steps.forEach((step, idx) => {
                const li = document.createElement('li');
                li.textContent = step;
                li.style.marginBottom = '6px';
                li.style.position = 'relative';
                li.style.paddingLeft = '20px';
                li.style.color = '#ffffff';
                li.style.fontSize = '0.95em';
                li.style.fontWeight = '500';
                li.style.lineHeight = '1.6';
                stepsList.appendChild(li);
            });
            
            stepsDiv.appendChild(stepsList);
            metaDiv.appendChild(stepsDiv);
        }
        
        // Кнопка создания тикета, если агент предлагает создать тикет, но тикет еще не создан
        if (!isUser && !metadata.ticket && shouldShowCreateTicketButton(content, metadata)) {
            const ticketButtonDiv = document.createElement('div');
            ticketButtonDiv.className = 'create-ticket-button-container';
            ticketButtonDiv.style.marginTop = '12px';
            ticketButtonDiv.style.paddingTop = '12px';
            ticketButtonDiv.style.borderTop = '1px solid rgba(0,0,0,0.08)';
            
            const ticketButton = document.createElement('button');
            ticketButton.className = 'btn-create-ticket';
            ticketButton.textContent = '🎫 Create Support Ticket';
            ticketButton.onclick = function() {
                createTicketFromMessage(content, userMessage || lastUserMessage, this);
            };
            
            ticketButtonDiv.appendChild(ticketButton);
            metaDiv.appendChild(ticketButtonDiv);
        }
        
        // Confidence badge
        if (metadata.confidence) {
            const confidenceDiv = document.createElement('div');
            confidenceDiv.className = `confidence-badge confidence-${metadata.confidence.toLowerCase()}`;
            confidenceDiv.style.marginTop = '10px';
            
            const confidenceColors = {
                'High': '#10b981',
                'Medium': '#f59e0b',
                'Low': '#ef4444'
            };
            
            confidenceDiv.innerHTML = `Confidence: <span style="color: ${confidenceColors[metadata.confidence] || '#a0a0b0'}; font-weight: 600;">${metadata.confidence}</span>`;
            metaDiv.appendChild(confidenceDiv);
        }
        
        contentDiv.appendChild(metaDiv);
    }
    
    messageDiv.appendChild(label);
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    
    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Show typing indicator
function showTypingIndicator() {
    const messagesContainer = document.getElementById('chat-messages');
    
    // Remove existing typing indicator
    const existing = messagesContainer.querySelector('.typing-indicator');
    if (existing) {
        existing.remove();
    }
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.innerHTML = `
        <span>Agent is thinking</span>
        <div class="typing-dots">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Copy to clipboard helper
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback could be added here
    });
}

// Show error
function showError(message) {
    const messagesContainer = document.getElementById('chat-messages');
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = '❌ Error: ' + message;
    messagesContainer.appendChild(errorDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Update status
function updateStatus(status, type = 'ready') {
    const statusEl = document.getElementById('status');
    statusEl.textContent = status;
    statusEl.className = `status-badge status-${type}`;
}

// Send message
async function sendMessage(message) {
    const sendButton = document.getElementById('send-button');
    const input = document.getElementById('message-input');
    
    // Disable form
    sendButton.disabled = true;
    input.disabled = true;
    updateStatus('Sending...', 'sending');
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                thread_id: currentThreadId
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Сохраняем последнее сообщение пользователя для создания тикета
        lastUserMessage = message;
        
        // Используем структурированный ответ
        if (data.answer) {
            const metadata = {
                sources: data.sources || [],
                next_steps: data.next_steps || [],
                actions_taken: data.actions_taken || [],
                confidence: data.confidence || 'Medium',
                ticket: data.ticket || null
            };
            
            addMessage(data.answer, false, metadata, message);
            updateStatus('Ready', 'ready');
        } else if (data.error) {
            throw new Error(data.answer || 'Server error');
        } else {
            throw new Error('Empty response from server. Please try again.');
        }
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message || 'Failed to send request');
        updateStatus('Error', 'error');
    } finally {
        // Enable form
        sendButton.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

// Handle form submission
document.getElementById('chat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!message) {
        return;
    }
    
    // Add user message
    addMessage(message, true);
    
    // Clear input field
    input.value = '';
    
    // Send request
    await sendMessage(message);
});

// Auto-resize textarea
const messageInput = document.getElementById('message-input');
messageInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

// Auto-focus on input field
messageInput.focus();

// Support Enter to send (Shift+Enter for new line)
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('chat-form').dispatchEvent(new Event('submit'));
    }
});

// Chat history
let historyPanelVisible = false;

function toggleHistory() {
    historyPanelVisible = !historyPanelVisible;
    const panel = document.getElementById('history-panel');
    const overlay = document.getElementById('history-overlay');
    
    if (panel && overlay) {
        if (historyPanelVisible) {
            overlay.classList.add('active');
            panel.classList.add('active');
            loadThreads();
            loadHistory();
        } else {
            overlay.classList.remove('active');
            panel.classList.remove('active');
        }
    }
}

// Close history when clicking overlay
document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById('history-overlay');
    if (overlay) {
        overlay.addEventListener('click', () => {
            toggleHistory();
        });
    }
});

// Bind event handlers after DOM loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHistoryHandlers);
} else {
    initHistoryHandlers();
}

function initHistoryHandlers() {
    const historyToggle = document.getElementById('history-toggle');
    const headerHistoryToggle = document.getElementById('header-history-toggle');
    const historyClose = document.getElementById('history-close');
    const historyRefresh = document.getElementById('history-refresh');
    const threadSelect = document.getElementById('thread-select');
    
    if (historyToggle) {
        historyToggle.addEventListener('click', toggleHistory);
    }
    
    if (headerHistoryToggle) {
        headerHistoryToggle.addEventListener('click', toggleHistory);
    }
    
    if (historyClose) {
        historyClose.addEventListener('click', toggleHistory);
    }
    
    if (historyRefresh) {
        historyRefresh.addEventListener('click', loadHistory);
    }
    
    if (threadSelect) {
        threadSelect.addEventListener('change', loadHistory);
    }
}

async function loadThreads() {
    try {
        const response = await fetch('/threads');
        const data = await response.json();
        
        const select = document.getElementById('thread-select');
        select.innerHTML = '<option value="">All threads</option>';
        
        data.threads.forEach(thread => {
            const option = document.createElement('option');
            option.value = thread.thread_id;
            option.textContent = `${thread.thread_id} (${thread.count} entries)`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading threads:', error);
    }
}

async function loadHistory() {
    const content = document.getElementById('history-content');
    content.innerHTML = '<p>Loading history...</p>';
    
    try {
        const threadSelect = document.getElementById('thread-select');
        const threadId = threadSelect.value || null;
        const url = threadId ? `/history?thread_id=${encodeURIComponent(threadId)}&limit=20` : '/history?limit=20';
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (!data.history || data.history.length === 0) {
            content.innerHTML = '<p>History is empty.</p>';
            return;
        }
        
        content.innerHTML = '';
        
        data.history.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';
            
            const toolBadge = item.tool_name ? `<span class="history-item-tool">${item.tool_name}</span>` : '';
            
            historyItem.innerHTML = `
                <div class="history-item-header">
                    <div>
                        <span class="history-item-id">ID: ${item.id}</span>
                        <span class="history-item-thread">${item.thread_id}</span>
                    </div>
                    ${toolBadge}
                </div>
                <div class="history-item-question">❓ ${item.user_message}</div>
                <div class="history-item-answer">💬 ${item.final_answer || 'No answer'}</div>
                <details class="history-item-details">
                    <summary>Tool call details</summary>
                    <strong>Arguments:</strong>
                    <pre>${JSON.stringify(item.tool_args, null, 2)}</pre>
                    <strong>Result:</strong>
                    <pre>${JSON.stringify(item.tool_result, null, 2)}</pre>
                </details>
            `;
            
            content.appendChild(historyItem);
        });
    } catch (error) {
        console.error('Error loading history:', error);
        content.innerHTML = `<p class="error-message">Error loading history: ${error.message}</p>`;
    }
}

// Load threads on page load (only if elements exist)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('thread-select')) {
            loadThreads();
        }
        initMenuToggle();
    });
} else {
    if (document.getElementById('thread-select')) {
        loadThreads();
    }
    initMenuToggle();
}

// Mobile menu toggle
function initMenuToggle() {
    const menuToggle = document.getElementById('menu-toggle');
    const infoPanel = document.getElementById('info-panel');
    
    if (!menuToggle || !infoPanel) {
        return;
    }
    
    function toggleMenu() {
        if (window.innerWidth <= 768) {
            const header = document.querySelector('header');
            if (header) {
                const headerHeight = header.offsetHeight;
                infoPanel.style.top = headerHeight + 'px';
            }
        }
        infoPanel.classList.toggle('active');
    }
    
    menuToggle.addEventListener('click', toggleMenu);
    
    // Close menu when clicking outside (only on mobile)
    if (window.innerWidth <= 768) {
        document.addEventListener('click', (e) => {
            if (infoPanel.classList.contains('active') && 
                !infoPanel.contains(e.target) && 
                !menuToggle.contains(e.target)) {
                infoPanel.classList.remove('active');
            }
        });
    }
}


