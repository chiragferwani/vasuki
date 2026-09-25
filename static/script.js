// === Vasuki Chat Frontend ===

const chatArea = document.getElementById('chatArea');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

let sessionId = localStorage.getItem('vasuki_session') || null;
let isWaiting = false;

// === Block DevTools ===

// Block right-click context menu
document.addEventListener('contextmenu', (e) => e.preventDefault());

// Block keyboard shortcuts for DevTools
document.addEventListener('keydown', (e) => {
    // F12
    if (e.key === 'F12') { e.preventDefault(); return; }
    // Ctrl+Shift+I (Inspect)
    if (e.ctrlKey && e.shiftKey && e.key === 'I') { e.preventDefault(); return; }
    // Ctrl+Shift+J (Console)
    if (e.ctrlKey && e.shiftKey && e.key === 'J') { e.preventDefault(); return; }
    // Ctrl+Shift+C (Element picker)
    if (e.ctrlKey && e.shiftKey && e.key === 'C') { e.preventDefault(); return; }
    // Ctrl+U (View source)
    if (e.ctrlKey && e.key === 'u') { e.preventDefault(); return; }
    // Ctrl+S (Save page)
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); return; }
});

// --- Auto-resize textarea ---
userInput.addEventListener('input', () => {
    userInput.style.height = '22px';
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

    if (isUser) {
        msgDiv.innerHTML = `
            <div class="user-avatar" title="You">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
            </div>
            <div class="message-content">
                <div class="message-name">You</div>
                <p>${escapeHtml(text)}</p>
            </div>
        `;
    } else {
        msgDiv.innerHTML = `
            <img src="/static/logo.jpeg" alt="Vasuki" class="message-avatar">
            <div class="message-content">
                <div class="message-name">Vasuki</div>
                <p>${escapeHtml(text)}</p>
            </div>
        `;
    }

    chatArea.appendChild(msgDiv);
    scrollToBottom();
}

// --- Show typing indicator ---
function showTyping() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message vasuki-message';
    typingDiv.id = 'typingIndicator';

    typingDiv.innerHTML = `
        <img src="/static/logo.jpeg" alt="Vasuki" class="message-avatar">
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
    if (!message) return;

    // Add user message
    addMessage(message, true);
    userInput.value = '';
    userInput.style.height = '22px';

    // Show typing indicator while waiting for model prefill
    showTyping();

    try {
        const response = await fetch('/api/chat/stream', {
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

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let msgDiv = null;
        let pElem = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith(':')) continue; // Ignore SSE heartbeats
                if (line.startsWith('data: ')) {
                    const payload = line.slice(6);
                    if (payload.startsWith('[SESSION:') && payload.endsWith(']')) {
                        sessionId = payload.slice(9, -1);
                        localStorage.setItem('vasuki_session', sessionId);
                    } else {
                        const token = payload.replace(/\\n/g, '\n');
                        if (!token) continue;

                        // Create Vasuki message card ONLY when the first token arrives
                        if (!msgDiv) {
                            hideTyping();
                            msgDiv = document.createElement('div');
                            msgDiv.className = 'message vasuki-message';
                            msgDiv.innerHTML = `
                                <img src="/static/logo.jpeg" alt="Vasuki" class="message-avatar">
                                <div class="message-content">
                                    <div class="message-name">Vasuki</div>
                                    <p></p>
                                </div>
                            `;
                            chatArea.appendChild(msgDiv);
                            pElem = msgDiv.querySelector('p');
                        }

                        pElem.textContent += token;
                        scrollToBottom();
                    }
                }
            }
        }

        if (!msgDiv) {
            hideTyping();
            addMessage("Vasuki remains silent... Speak again, mortal.");
        } else if (!pElem.textContent.trim()) {
            pElem.textContent = "Vasuki remains silent... Speak again, mortal.";
        }

    } catch (error) {
        hideTyping();
        addMessage('The serpent stirs uneasily... Something went wrong. Try again, mortal.');
        console.error('Chat error:', error);
    } finally {
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
            <img src="/static/logo.jpeg" alt="Vasuki" class="message-avatar">
            <div class="message-content">
                <div class="message-name">Vasuki</div>
                <p>Sssso... a mortal dares approach the King of Serpents. I am Vasuki, Nagaraja, whose coils once churned the Ocean of Milk itself. Speak your purpose, little one. But know this — I guard secrets that even the gods have failed to wrest from me.</p>
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
