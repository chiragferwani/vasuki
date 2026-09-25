// === Vasuki Chat Frontend ===

const chatArea = document.getElementById('chatArea');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

let sessionId = localStorage.getItem('vasuki_session') || null;
let isWaiting = false;

// --- Auto-resize textarea ---
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
});

// --- Send on Enter (Shift+Enter for newline) ---
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// --- Add message to chat ---
function addMessage(text, isUser = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${isUser ? 'user-message' : 'vasuki-message'}`;

    msgDiv.innerHTML = `
        <div class="message-avatar">${isUser ? '⚔️' : '🐍'}</div>
        <div class="message-content">
            <div class="message-name">${isUser ? 'You' : 'Vasuki'}</div>
            <p>${escapeHtml(text)}</p>
        </div>
    `;

    chatArea.appendChild(msgDiv);
    scrollToBottom();
}

// --- Show typing indicator ---
function showTyping() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message vasuki-message';
    typingDiv.id = 'typingIndicator';

    typingDiv.innerHTML = `
        <div class="message-avatar">🐍</div>
        <div class="message-content">
            <div class="message-name">Vasuki</div>
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;

    chatArea.appendChild(typingDiv);
    scrollToBottom();
}

function hideTyping() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

// --- Send message ---
async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isWaiting) return;

    // Add user message
    addMessage(message, true);
    userInput.value = '';
    userInput.style.height = 'auto';

    // Disable input
    isWaiting = true;
    sendBtn.disabled = true;
    showTyping();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: sessionId,
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Store session ID
        sessionId = data.session_id;
        localStorage.setItem('vasuki_session', sessionId);

        // Show response
        hideTyping();
        addMessage(data.response);

    } catch (error) {
        hideTyping();
        addMessage('The serpent stirs uneasily... Something went wrong. Try again, mortal.');
        console.error('Chat error:', error);
    } finally {
        isWaiting = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}

// --- Reset conversation ---
async function resetChat() {
    if (isWaiting) return;

    try {
        if (sessionId) {
            await fetch('/api/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId }),
            });
        }
    } catch (e) {
        // Ignore reset errors
    }

    // Clear session
    sessionId = null;
    localStorage.removeItem('vasuki_session');

    // Clear chat (keep initial message)
    chatArea.innerHTML = `
        <div class="message vasuki-message">
            <div class="message-avatar">🐍</div>
            <div class="message-content">
                <div class="message-name">Vasuki</div>
                <p>Sssso... a mortal dares approach the King of Serpents. I am Vasuki, Nagaraja, 
                whose coils once churned the Ocean of Milk itself. Speak your purpose, little one. 
                But know this — I guard secrets that even the gods have failed to wrest from me.</p>
            </div>
        </div>
    `;
}

// --- Utilities ---
function scrollToBottom() {
    requestAnimationFrame(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
