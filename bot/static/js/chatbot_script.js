document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element References ---
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const chatLog = document.getElementById('chat-log');
    const chatLogContainer = document.getElementById('chat-log-container');
    const loadingIndicator = document.getElementById('loading-indicator');
    const errorMessageDiv = document.getElementById('error-message');
    const newChatButton = document.getElementById('new-chat-button');
    const conversationsList = document.getElementById('conversations-list');
    const clearCurrentChatButton = document.getElementById('clear-current-chat-button');
    const deleteAllButton = document.getElementById('delete-all-button');
    const searchConversationsInput = document.getElementById('search-conversations-input'); // Added

    // Sidebar Elements
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggleOpenBtn = document.getElementById('sidebar-toggle-open');
    const sidebarToggleCloseBtn = document.getElementById('sidebar-toggle-close');

    let currentConversationId = null;
    let currentMessages = []; 

    function openSidebar() {
        if (sidebar) sidebar.classList.add('open');
        document.body.classList.add('sidebar-open-overlay');
        if (sidebarToggleCloseBtn) sidebarToggleCloseBtn.focus();
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        document.body.classList.remove('sidebar-open-overlay');
        if (sidebarToggleOpenBtn && window.innerWidth <= 768) sidebarToggleOpenBtn.focus();
    }

    if (sidebarToggleOpenBtn) {
        sidebarToggleOpenBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openSidebar();
        });
    }
    if (sidebarToggleCloseBtn) {
        sidebarToggleCloseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeSidebar();
        });
    }

    document.body.addEventListener('click', (event) => {
        if (document.body.classList.contains('sidebar-open-overlay') &&
            sidebar && !sidebar.contains(event.target) &&
            event.target !== sidebarToggleOpenBtn &&
            (!sidebarToggleOpenBtn || !sidebarToggleOpenBtn.contains(event.target))
        ) {
            closeSidebar();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && sidebar && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    });

    if (userInput && sendButton) {
        userInput.addEventListener('input', () => {
            userInput.style.height = 'auto';
            let scrollHeight = userInput.scrollHeight;
            const maxHeight = parseInt(window.getComputedStyle(userInput).maxHeight, 10) || 200;

            if (scrollHeight > maxHeight) {
                userInput.style.height = maxHeight + 'px';
                userInput.style.overflowY = 'auto';
            } else {
                userInput.style.height = scrollHeight + 'px';
                userInput.style.overflowY = 'hidden';
            }
            sendButton.disabled = userInput.value.trim() === '';
        });
        sendButton.disabled = true;
    }


    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (!messageText) return;

        appendMessage('user', messageText);
        currentMessages.push({ sender: 'user', text: messageText });

        userInput.value = '';
        userInput.style.height = 'auto';
        if (userInput.style.maxHeight) userInput.style.overflowY = 'hidden';
        sendButton.disabled = true;

        loadingIndicator.style.display = 'flex';
        errorMessageDiv.style.display = 'none';
        errorMessageDiv.textContent = '';

        try {
            const conversationHistoryForAPI = currentMessages
                .slice(0, -1)
                .filter(msg => msg.text !== null && msg.text !== undefined && String(msg.text).trim() !== '')
                .map(msg => ({
                    role: msg.sender === 'user' ? 'user' : 'model',
                    parts: [{ text: String(msg.text) }]
                }));

            const payload = {
                prompt: messageText,
                conversation: conversationHistoryForAPI
            };
            console.log("Sending to /generate:", JSON.stringify(payload, null, 2));


            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errorData = await response.json();
                console.error("Error response from server:", errorData);
                throw new Error(errorData.details || errorData.error || `HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            if (data.generated_text) {
                appendMessage('bot', data.generated_text);
                currentMessages.push({ sender: 'bot', text: data.generated_text });
                saveCurrentConversation();
            } else if (data.error) {
                 console.error("Server returned an error in JSON:", data.error);
                 errorMessageDiv.textContent = `Server Error: ${data.error}`;
                 errorMessageDiv.style.display = 'block';
            } else {
                console.warn("Received response from AI, but 'generated_text' was empty or missing.", data);
                appendMessage('bot', "I received a response, but it was empty. Please try rephrasing.");
            }

        } catch (error) {
            console.error('Error during sendMessage fetch or processing:', error);
            errorMessageDiv.textContent = `Error: ${error.message}`;
            errorMessageDiv.style.display = 'block';
        } finally {
            loadingIndicator.style.display = 'none';
        }
    }

    function createAvatarElement(sender) {
        const avatarDiv = document.createElement('div');
        avatarDiv.classList.add('avatar');
        avatarDiv.textContent = sender === 'user' ? 'U' : 'AI';
        return avatarDiv;
    }

    function appendMessage(sender, text) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');

        const avatarElement = createAvatarElement(sender);

        const textDiv = document.createElement('div');
        textDiv.classList.add('text');
        textDiv.textContent = text; 

        if (sender === 'user') {
            messageDiv.appendChild(textDiv);
            messageDiv.appendChild(avatarElement);
        } else {
            messageDiv.appendChild(avatarElement);
            messageDiv.appendChild(textDiv);
        }

        if (chatLog) chatLog.appendChild(messageDiv);

        requestAnimationFrame(() => {
            if (chatLogContainer) {
                 chatLogContainer.scrollTop = chatLogContainer.scrollHeight;
            }
        });
    }


    if (sendButton) sendButton.addEventListener('click', sendMessage);
    if (userInput) {
        userInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (!sendButton.disabled) {
                    sendMessage();
                }
            }
        });
    }

    if (clearCurrentChatButton) {
        clearCurrentChatButton.addEventListener('click', () => {
            if (confirm("Are you sure you want to clear the current chat messages? This will not delete the saved conversation if it exists.")) {
                if(chatLog) chatLog.innerHTML = ''; // Only clear the visual log
                errorMessageDiv.style.display = 'none';
                errorMessageDiv.textContent = '';
               
            }
        });
    }

    function generateConversationId() {
        return `chat_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    }

    function getConversationTitle(messages) {
        const firstUserMessage = messages.find(m => m.sender === 'user' && m.text && String(m.text).trim() !== '');
        if (firstUserMessage) {
            const text = String(firstUserMessage.text);
            return text.substring(0, 35).trim() + (text.length > 35 ? "..." : "");
        }
        return "Chat Session";
    }

    function saveCurrentConversation() {
        if (!currentMessages.length) return;

        if (!currentConversationId) {
            currentConversationId = generateConversationId();
        }

        const conversationData = {
            id: currentConversationId,
            title: getConversationTitle(currentMessages),
            messages: currentMessages,
            timestamp: Date.now()
        };
        localStorage.setItem(`conversation_${currentConversationId}`, JSON.stringify(conversationData));
        updateConversationList();
    }

    function loadConversation(id) {
        const savedData = localStorage.getItem(`conversation_${id}`);
        if (savedData) {
            try {
                const conversation = JSON.parse(savedData);
                if (chatLog) chatLog.innerHTML = '';
                currentMessages = conversation.messages || [];
                currentConversationId = conversation.id;

                currentMessages.forEach(msg => {
                    if (msg && typeof msg.sender === 'string' && msg.text !== null && msg.text !== undefined) {
                        appendMessage(msg.sender, String(msg.text));
                    } else {
                        console.warn("Skipping message with invalid sender or null/undefined text during load:", msg);
                    }
                });

                errorMessageDiv.style.display = 'none';
                errorMessageDiv.textContent = '';
                if (userInput) userInput.focus();
                closeSidebar();
            } catch (e) {
                console.error("Error parsing conversation data from localStorage:", e);
                localStorage.removeItem(`conversation_${id}`);
                appendMessage('bot', "Sorry, couldn't load that conversation. It might be corrupted and has been removed.");
            } finally {
                updateConversationList(); 
            }
        } else {
            console.warn(`No data found in localStorage for conversation ID: ${id}`);
        }
    }

    function updateConversationList() {
        if (!conversationsList) return;
        conversationsList.innerHTML = '';
        const keys = Object.keys(localStorage).filter(key => key.startsWith('conversation_'));

        let savedConversations = keys.map(key => {
            try {
                const conv = JSON.parse(localStorage.getItem(key));
                if (conv && conv.id && conv.title && typeof conv.timestamp === 'number' && Array.isArray(conv.messages)) {
                    return conv;
                }
                console.warn("Removing invalid conversation data from localStorage:", key, conv);
                localStorage.removeItem(key);
                return null;
            } catch (e) {
                console.warn("Could not parse conversation from localStorage for list:", key, e);
                localStorage.removeItem(key);
                return null;
            }
        }).filter(conv => conv !== null);

        savedConversations.sort((a, b) => b.timestamp - a.timestamp);

        const searchTerm = searchConversationsInput ? searchConversationsInput.value.toLowerCase().trim() : '';
        const filteredConversations = searchTerm
            ? savedConversations.filter(conv => conv.title.toLowerCase().includes(searchTerm))
            : savedConversations;

        filteredConversations.forEach(conversation => {
            const listItem = document.createElement('li');
            listItem.dataset.conversationId = conversation.id;

            const detailsDiv = document.createElement('div');
            detailsDiv.classList.add('conv-details');
            detailsDiv.addEventListener('click', () => loadConversation(conversation.id)); // Load on details click

            const titleSpan = document.createElement('span');
            titleSpan.classList.add('conv-title');
            titleSpan.textContent = conversation.title;

            const date = new Date(conversation.timestamp);
            const timeString = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const dateString = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            const timestampSpan = document.createElement('span');
            timestampSpan.classList.add('conv-timestamp');
            timestampSpan.textContent = `${dateString}, ${timeString}`;

            detailsDiv.appendChild(titleSpan);
            detailsDiv.appendChild(timestampSpan);

            const deleteButton = document.createElement('button');
            deleteButton.classList.add('delete-conversation-button');
            deleteButton.title = `Delete chat: "${conversation.title}"`;
            deleteButton.innerHTML = '<i class="fas fa-trash-alt"></i>';

            deleteButton.addEventListener('click', (e) => {
                e.stopPropagation(); 
                if (confirm(`Are you sure you want to delete the conversation: "${conversation.title}"? This cannot be undone.`)) {
                    localStorage.removeItem(`conversation_${conversation.id}`);
                    
                    if (currentConversationId === conversation.id) {
                        currentConversationId = null;
                        currentMessages = [];
                        if (chatLog) chatLog.innerHTML = '';
                        errorMessageDiv.style.display = 'none';
                        errorMessageDiv.textContent = '';
                        if (userInput) {
                            userInput.value = '';
                            userInput.style.height = 'auto';
                        }
                        if (sendButton) sendButton.disabled = true;

                        updateConversationList(); 

                        const remainingKeys = Object.keys(localStorage).filter(key => key.startsWith('conversation_'));
                        if (remainingKeys.length > 0) {
                            const allRemainingConversations = remainingKeys.map(k => {
                                try { return JSON.parse(localStorage.getItem(k)); } catch { return null; }
                            }).filter(c => c && c.id && typeof c.timestamp === 'number');
                            
                            if (allRemainingConversations.length > 0) {
                                allRemainingConversations.sort((a, b) => b.timestamp - a.timestamp);
                                loadConversation(allRemainingConversations[0].id);
                            } else {
                                startNewChatSession(true, "The active chat was deleted. No other chats found.");
                            }
                        } else {
                             startNewChatSession(true, "The last chat was deleted. Start a new one!");
                        }
                    } else {
                        updateConversationList(); 
                    }
                }
            });

            listItem.appendChild(detailsDiv);
            listItem.appendChild(deleteButton);

            if (conversation.id === currentConversationId) {
                listItem.classList.add('active');
            }
            conversationsList.appendChild(listItem);
        });
    }

    if (searchConversationsInput) {
        searchConversationsInput.addEventListener('input', updateConversationList);
    }
    
    function startNewChatSession(displayWelcomeMessage = true, customWelcomeMessage = null) {
        currentConversationId = null;
        currentMessages = [];
        if (chatLog) chatLog.innerHTML = '';
        errorMessageDiv.style.display = 'none';
        errorMessageDiv.textContent = '';
        if (userInput) {
            userInput.value = '';
            userInput.style.height = 'auto';
            userInput.focus();
        }
        if (sendButton) sendButton.disabled = true;

        if (displayWelcomeMessage) {
            const welcomeMsg = customWelcomeMessage || 'New chat started. How can I help you today?';
            appendMessage('bot', welcomeMsg);
        }
        updateConversationList(); 
        closeSidebar();
    }


    if (newChatButton) {
        newChatButton.addEventListener('click', () => {
            startNewChatSession(true, 'New chat started. How can I help you today?');
        });
    }

    if (deleteAllButton) {
        deleteAllButton.addEventListener('click', () => {
            if (confirm("Are you sure you want to delete ALL saved conversations? This cannot be undone.")) {
                const keys = Object.keys(localStorage).filter(key => key.startsWith('conversation_'));
                keys.forEach(key => localStorage.removeItem(key));
                
                // Reset to a fresh state similar to new chat
                startNewChatSession(true, 'All conversations have been deleted. Feel free to start a new chat!');
            }
        });
    }

    //Initial Load ---
    function initializeChat() {
        updateConversationList(); 
        const keys = Object.keys(localStorage).filter(key => key.startsWith('conversation_'));
        let loadedConversation = false;

        if (keys.length > 0) {
            const allConversations = keys.map(k => {
                try { 
                    const conv = JSON.parse(localStorage.getItem(k));
                    if (conv && conv.id && conv.title && typeof conv.timestamp === 'number' && Array.isArray(conv.messages)) {
                        return conv;
                    }
                    localStorage.removeItem(k); 
                    return null;
                }
                catch { 
                    localStorage.removeItem(k);
                    return null; 
                }
            }).filter(c => c !== null);

            if (allConversations.length > 0) {
                allConversations.sort((a,b) => b.timestamp - a.timestamp);
                loadConversation(allConversations[0].id);
                loadedConversation = true;
            }
        }
        
        if (!loadedConversation) {
            startFreshWelcome();
        }
        if (userInput) userInput.focus();
    }

    function startFreshWelcome() {
        currentConversationId = null;
        currentMessages = [];
        if (chatLog) chatLog.innerHTML = '';
        const initialWelcome = 'Welcome to NovaTech AI Assistant! How can I assist you with university information today?';
        appendMessage('bot', initialWelcome);
        updateConversationList(); 
    }

    initializeChat();
});