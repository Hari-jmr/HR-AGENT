'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

type Role = 'user' | 'assistant';

type ChatSection = {
  kind: 'paragraph' | 'list';
  title?: string | null;
  content?: string | null;
  items: string[];
};

type ChatStructuredResponse = {
  summary: string;
  sections: ChatSection[];
};

type Message = {
  role: Role;
  content: string;
  structured?: ChatStructuredResponse;
};

type Employee = {
  name?: string;
  job_title?: string;
  department?: string;
  emp_code?: string;
};

type AuthState = 'loading' | 'guest' | 'authenticated';

type WorkspaceView = 'chat';

type SuggestedPrompt = {
  title: string;
  subtitle: string;
  prompt: string;
};

const suggestedPrompts: SuggestedPrompt[] = [
  {
    title: 'Show me my leave balance',
    subtitle: 'casual, sick, earned leave summary',
    prompt: 'Show my leave balance',
  },
  {
    title: 'Summarize my latest payroll',
    subtitle: 'net pay, deductions, and latest month',
    prompt: 'What was my latest payroll summary?',
  },
  {
    title: 'Help me understand attendance',
    subtitle: 'last 30 days with present and absent counts',
    prompt: 'Summarize attendance for the last 30 days',
  },
];

function trimLabel(value: string, max = 26) {
  if (value.length <= max) {
    return value;
  }

  return `${value.slice(0, max - 1)}…`;
}

function normalizeAssistantContent(value: string) {
  return value
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/`+/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}


function normalizeStructuredText(value: string) {
  return normalizeAssistantContent(value).replace(/:$/, '').trim();
}

export function HrAgentApp() {
  const [authState, setAuthState] = useState<AuthState>('loading');
  const [activeView, setActiveView] = useState<WorkspaceView>('chat');
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [isHr, setIsHr] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [input, setInput] = useState('');
  const [loginError, setLoginError] = useState('');
  const [chatError, setChatError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const feedRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void loadSession();
  }, []);

  useEffect(() => {
    const feed = feedRef.current;
    if (feed) {
      feed.scrollTop = feed.scrollHeight;
    }
  }, [messages, isSubmitting, authState]);

  async function loadSession() {
    try {
      const response = await fetch('/backend/auth/me', {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
      });

      if (!response.ok) {
        setAuthState('guest');
        return;
      }

      const data = await response.json();
      if (!data.authenticated) {
        setAuthState('guest');
        return;
      }

      setEmployee(data.employee || null);
      setIsHr(Boolean(data.is_hr));
      setActiveView('chat');
      setMessages(
        Array.isArray(data.chat_history)
          ? data.chat_history.filter((entry: Message) => entry.role === 'user' || entry.role === 'assistant')
          : []
      );
      setAuthState('authenticated');
    } catch {
      setAuthState('guest');
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoggingIn(true);
    setLoginError('');

    try {
      const response = await fetch('/backend/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(loginForm),
      });
      const data = await response.json();

      if (!response.ok) {
        setLoginError(data.error || 'Unable to sign in.');
        return;
      }

      setEmployee(data.employee || null);
      setIsHr(Boolean(data.is_hr));
      setMessages([]);
      setActiveView('chat');
      setAuthState('authenticated');
      setShowLoginModal(false);
      setLoginForm({ username: '', password: '' });
    } catch {
      setLoginError('Unable to reach the backend. Make sure the FastAPI server is running on port 5000.');
    } finally {
      setIsLoggingIn(false);
    }
  }

  async function handleLogout() {
    await fetch('/backend/auth/logout', {
      method: 'POST',
      credentials: 'include',
    });

    setMessages([]);
    setEmployee(null);
    setIsHr(false);
    setInput('');
    setChatError('');
    setActiveView('chat');
    setAuthState('guest');
  }

  async function handleClear() {
    await fetch('/backend/clear', {
      method: 'POST',
      credentials: 'include',
    });
    setMessages([]);
    setChatError('');
  }

  async function handleSend(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const prompt = input.trim();
    if (!prompt || isSubmitting) {
      return;
    }

    if (authState !== 'authenticated') {
      setLoginError('Sign in to ask questions about your HR data.');
      setShowLoginModal(true);
      return;
    }

    const nextUserMessage: Message = { role: 'user', content: prompt };
    setMessages((current) => [...current, nextUserMessage]);
    setInput('');
    setChatError('');
    setIsSubmitting(true);

    try {
      const response = await fetch('/backend/chat', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: prompt }),
      });

      if (response.status === 401) {
        setAuthState('guest');
        setMessages([]);
        return;
      }

      const data = await response.json();

      if (!response.ok || data.error) {
        const errorMessage = data.error || 'The assistant could not complete that request.';
        setChatError(errorMessage);
        setMessages((current) => [...current, { role: 'assistant', content: errorMessage }]);
        return;
      }

      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: data.response || '',
          structured: data.structured,
        },
      ]);
    } catch {
      const fallback = 'Connection error. Confirm the FastAPI app is running and reachable.';
      setChatError(fallback);
      setMessages((current) => [...current, { role: 'assistant', content: fallback }]);
    } finally {
      setIsSubmitting(false);
    }
  }

  const statusLabel = useMemo(() => {
    if (authState === 'loading') {
      return 'Checking session';
    }
    if (authState === 'guest') {
      return 'Sign in required';
    }
    return isHr ? 'HR mode' : 'Employee mode';
  }, [authState, isHr]);

  const activeChatTitle = useMemo(() => {
    const firstUserMessage = messages.find((message) => message.role === 'user');
    return firstUserMessage ? trimLabel(firstUserMessage.content) : 'New conversation';
  }, [messages]);

  const modelName = 'JMR HR Agent';
  const welcomeGreeting = employee?.name
    ? `Hello ${employee.name}! I'm your HR Assistant. Ask me anything!`
    : "Hello Employee! I'm your HR Assistant. Ask me anything!";

  function promptSignIn() {
    setLoginError('Sign in to ask questions about your queries to HR Agent.');
    setShowLoginModal(true);
  }

  function focusPrompt() {
    inputRef.current?.focus();
  }

  function renderSidebar() {
    const navItems = authState === 'authenticated'
      ? [
          { key: 'chat' as const, label: activeChatTitle, hint: 'conversation' },
        ]
      : [
          { key: 'chat' as const, label: 'Payroll', hint: 'secure assistant' },
        ];

    return (
      <aside className="ow-sidebar">
        <div className="ow-sidebar-header">
          <span>JMR HR Agent</span>
        </div>

        <div className="ow-sidebar-group">
          <p className="ow-sidebar-title">JMR HR Agent</p>
          {navItems.map((item) => (
            <button
              className={`ow-nav-item ${activeView === item.key ? 'active' : ''}`}
              type="button"
              key={item.key}
              onClick={() => {
                setActiveView(item.key);
                if (item.key === 'chat') {
                  focusPrompt();
                }
              }}
            >
              <span className={item.key === 'chat' ? 'ow-nav-mark' : 'ow-nav-dot square'}>{item.key === 'chat' ? '#' : ''}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>

        <div className="ow-sidebar-spacer" />

        {authState === 'authenticated' ? (
          <div className="ow-user-card">
            <div className="ow-user-avatar">{(employee?.name || 'E').slice(0, 1).toUpperCase()}</div>
            <div>
              <div className="ow-user-name">{employee?.name || 'Employee'}</div>
              <div className="ow-user-meta">{statusLabel}</div>
            </div>
          </div>
        ) : null}
      </aside>
    );
  }

  function renderModelLockup() {
    return (
      <div className="ow-model-lockup">
        <h1>{modelName}</h1>
      </div>
    );
  }

  function renderPromptComposer() {
    const isGuestComposer = authState !== 'authenticated';

    if (isGuestComposer) {
      return (
        <div className="ow-composer guest-locked">
          <button className="ow-guest-composer-field" type="button" onClick={promptSignIn}>
            Sign in to ask HR questions
          </button>
          <div className="ow-composer-footer">
            <button className="ow-send-button" type="button" onClick={promptSignIn}>
              ➜
            </button>
          </div>
        </div>
      );
    }

    return (
      <form className="ow-composer" onSubmit={handleSend}>
        <input
          ref={inputRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="How can I help you today?"
        />
        <div className="ow-composer-footer">
          <button className="ow-send-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? '...' : '➜'}
          </button>
        </div>
      </form>
    );
  }

  function renderLoginModal() {
    if (!showLoginModal) {
      return null;
    }

    return (
      <div className="ow-auth-modal" role="dialog" aria-modal="true" aria-label="Sign in">
        <div className="ow-auth-backdrop" onClick={() => setShowLoginModal(false)} />
        <form className="ow-auth-dialog" onSubmit={handleLogin}>
          <div className="ow-auth-dialog-header">
            <h2>Sign in</h2>
            <button className="ow-close-button" type="button" onClick={() => setShowLoginModal(false)}>
              ×
            </button>
          </div>
          <p>Use your existing HRMS employee credentials.</p>
          <input
            type="text"
            value={loginForm.username}
            onChange={(event) => setLoginForm((current) => ({ ...current, username: event.target.value }))}
            placeholder="Username"
            autoComplete="username"
            required
          />
          <input
            type="password"
            value={loginForm.password}
            onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
            placeholder="Password"
            autoComplete="current-password"
            required
          />
          {loginError ? <p className="ow-error-text">{loginError}</p> : null}
          <button className="ow-auth-button" type="submit" disabled={isLoggingIn}>
            {isLoggingIn ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    );
  }

  function renderSuggestions() {
    return (
      <div className="ow-suggestions">
        <div className="ow-suggestions-title">Suggested</div>
        {suggestedPrompts.map((item) => (
          <button
            className="ow-suggestion-item"
            key={item.title}
            type="button"
            onClick={() => {
              setInput(item.prompt);
              focusPrompt();
            }}
          >
            <strong>{item.title}</strong>
            <span>{item.subtitle}</span>
          </button>
        ))}
      </div>
    );
  }

  function renderMessageBody(message: Message) {
    if (message.role === 'assistant') {
      if (message.structured) {
        return (
          <div className="ow-structured-response">
            <p>{normalizeStructuredText(message.structured.summary)}</p>
            {message.structured.sections.map((section, index) => {
              if (section.kind === 'list') {
                return (
                  <ul key={`section-${index}`}>
                    {section.items.map((item, itemIndex) => (
                      <li key={`item-${index}-${itemIndex}`}>{normalizeStructuredText(item)}</li>
                    ))}
                  </ul>
                );
              }

              return section.content ? <p key={`section-${index}`}>{normalizeStructuredText(section.content)}</p> : null;
            })}
          </div>
        );
      }
      return normalizeAssistantContent(message.content);
    }

    return message.content;
  }

  if (authState === 'loading') {
    return (
      <main className="ow-shell">
        {renderSidebar()}
        <section className="ow-main ow-centered-main">
          <div className="ow-loading">Preparing workspace...</div>
        </section>
      </main>
    );
  }

  if (authState === 'guest') {
    return (
      <main className="ow-shell">
        {renderSidebar()}
        <section className="ow-main">
          <div className="ow-main-toolbar guest only-actions">
            <div className="ow-toolbar-actions">
              <span className="ow-mode-pill">{statusLabel}</span>
              <button className="ow-toolbar-button" type="button" onClick={() => setShowLoginModal(true)}>
                Sign in
              </button>
            </div>
          </div>

          <div className="ow-centered-main ow-empty-state guest">
            <div className="ow-center-stack guest">
              {renderModelLockup()}
              {renderPromptComposer()}
              {renderSuggestions()}
            </div>
          </div>
        </section>
        {renderLoginModal()}
      </main>
    );
  }

  return (
    <main className="ow-shell">
      {renderSidebar()}

      <section className="ow-main">
        <div className="ow-main-toolbar">
          <div>
            <span className="ow-toolbar-label">Active assistant</span>
            <strong>{employee?.name || 'Employee'}</strong>
          </div>
          <div className="ow-toolbar-actions">
            <span className="ow-mode-pill">{statusLabel}</span>
            <button className="ow-toolbar-button" type="button" onClick={handleClear}>
              Clear
            </button>
            <button className="ow-toolbar-button" type="button" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        </div>

        {activeView === 'chat' && messages.length === 0 ? (
          <div className="ow-centered-main ow-empty-state">
            <div className="ow-center-stack">
              {renderModelLockup()}
              <p className="ow-panel-copy">{welcomeGreeting}</p>
              {renderPromptComposer()}
              {chatError ? <p className="ow-error-text">{chatError}</p> : null}
              {renderSuggestions()}
            </div>
          </div>
        ) : null}

        {activeView === 'chat' && messages.length > 0 ? (
          <div className="ow-chat-layout">
            <div className="ow-message-scroll" ref={feedRef}>
              {messages.map((message, index) => (
                <article key={`${message.role}-${index}`} className={`ow-message ${message.role}`}>
                  <div className="ow-message-name">{message.role === 'user' ? 'You' : 'Assistant'}</div>
                  <div className="ow-message-body">{renderMessageBody(message)}</div>
                </article>
              ))}

              {isSubmitting ? (
                <div className="ow-thinking-row" aria-label="Assistant is thinking">
                  <span />
                  <span />
                  <span />
                </div>
              ) : null}
            </div>

            <div className="ow-chat-compose-wrap bottom">
              {chatError ? <p className="ow-error-text">{chatError}</p> : null}
              {renderPromptComposer()}
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}