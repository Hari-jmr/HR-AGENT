"""
Session Memory Service — Temporary memory during a single chat session.

Stores:
- Conversation history
- Last discussed topics (for follow-up questions)
- Query context (what was last asked)
- Session metadata
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionMemory:
    """Temporary memory for a single chat session."""
    
    employee_id: int
    employee_name: str = ""
    emp_code: str = ""
    
    conversation: list[dict] = field(default_factory=list)
    
    last_topic: Optional[str] = None
    last_query_type: Optional[str] = None
    last_entity: Optional[str] = None
    
    queries_made: list[str] = field(default_factory=list)
    
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation.append({
            'role': role,
            'content': content,
            'timestamp': time.time()
        })
        self.last_activity = time.time()
        
        if len(self.conversation) > 30:
            self.conversation = self.conversation[-30:]
    
    def set_context(self, topic: str, query_type: str, entity: Optional[str] = None):
        """Set current conversation context."""
        self.last_topic = topic
        self.last_query_type = query_type
        self.last_entity = entity
        self.queries_made.append(f"{query_type}:{topic}")
        if len(self.queries_made) > 10:
            self.queries_made = self.queries_made[-10:]
    
    def get_context_summary(self) -> str:
        """Get a summary of current context for follow-up questions."""
        parts = []
        if self.last_topic:
            parts.append(f"last discussed: {self.last_topic}")
        if self.last_query_type:
            parts.append(f"query type: {self.last_query_type}")
        if self.last_entity:
            parts.append(f"entity: {self.last_entity}")
        return " | ".join(parts) if parts else "new conversation"
    
    def get_recent_messages(self, n: int = 6) -> list[dict]:
        """Get last n messages for LLM context."""
        return [
            {'role': m['role'], 'content': m['content']}
            for m in self.conversation[-n:]
        ]
    
    def get_last_user_message(self) -> Optional[str]:
        """Get the last user message."""
        for msg in reversed(self.conversation):
            if msg['role'] == 'user':
                return msg['content']
        return None
    
    def get_last_assistant_message(self) -> Optional[str]:
        """Get the last assistant message."""
        for msg in reversed(self.conversation):
            if msg['role'] == 'assistant':
                return msg['content']
        return None
    
    def is_follow_up(self, message: str) -> bool:
        """Check if message is a follow-up to previous conversation."""
        follow_up_indicators = [
            'what about', 'how about', 'and my', 'also', 'what is my',
            'show me my', 'my other', 'and the', 'what else', 'that too',
            'same for', 'what about my'
        ]
        msg_lower = message.lower().strip()
        return any(msg_lower.startswith(indicator) for indicator in follow_up_indicators)
    
    def resolve_reference(self, message: str) -> str:
        """Resolve pronoun references to actual entity."""
        if not self.last_entity:
            return message
        
        import re
        pronouns = ['it', 'that', 'this', 'the same']
        
        for pronoun in pronouns:
            pattern = r'\b' + pronoun + r'\b'
            if re.search(pattern, message.lower()):
                return re.sub(pattern, self.last_entity, message, count=1, flags=re.IGNORECASE)
        
        return message
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for session storage."""
        return {
            'employee_id': self.employee_id,
            'employee_name': self.employee_name,
            'emp_code': self.emp_code,
            'conversation': self.conversation,
            'last_topic': self.last_topic,
            'last_query_type': self.last_query_type,
            'last_entity': self.last_entity,
            'queries_made': self.queries_made,
            'created_at': self.created_at,
            'last_activity': self.last_activity,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SessionMemory':
        """Deserialize from session dictionary."""
        memory = cls(
            employee_id=data.get('employee_id', 0),
            employee_name=data.get('employee_name', ''),
            emp_code=data.get('emp_code', ''),
            conversation=data.get('conversation', []),
            last_topic=data.get('last_topic'),
            last_query_type=data.get('last_query_type'),
            last_entity=data.get('last_entity'),
            queries_made=data.get('queries_made', []),
            created_at=data.get('created_at', time.time()),
            last_activity=data.get('last_activity', time.time()),
        )
        return memory


class SessionMemoryManager:
    """Manages session memory for chat sessions."""
    
    MEMORY_KEY = 'session_memory'
    
    def __init__(self, session: dict):
        self.session = session
    
    def get_memory(self) -> Optional[SessionMemory]:
        """Get current session memory."""
        data = self.session.get(self.MEMORY_KEY)
        if data:
            return SessionMemory.from_dict(data)
        return None
    
    def initialize(self, employee_info: dict) -> SessionMemory:
        """Initialize new session memory."""
        memory = SessionMemory(
            employee_id=employee_info.get('employee_id', 0),
            employee_name=employee_info.get('name', ''),
            emp_code=employee_info.get('emp_code', ''),
        )
        self._save(memory)
        return memory
    
    def get_or_create(self, employee_info: dict) -> SessionMemory:
        """Get existing or create new session memory."""
        memory = self.get_memory()
        if memory and memory.employee_id == employee_info.get('employee_id'):
            return memory
        return self.initialize(employee_info)
    
    def add_user_message(self, message: str):
        """Add user message to memory."""
        memory = self.get_memory()
        if memory:
            memory.add_message('user', message)
            self._save(memory)
    
    def add_assistant_message(self, message: str):
        """Add assistant message to memory."""
        memory = self.get_memory()
        if memory:
            memory.add_message('assistant', message)
            self._save(memory)
    
    def update_context(self, topic: str, query_type: str, entity: Optional[str] = None):
        """Update conversation context."""
        memory = self.get_memory()
        if memory:
            memory.set_context(topic, query_type, entity)
            self._save(memory)
    
    def get_context_for_llm(self, n: int = 6) -> list[dict]:
        """Get recent messages for LLM context."""
        memory = self.get_memory()
        if memory:
            return memory.get_recent_messages(n)
        return []
    
    def enhance_message(self, message: str) -> str:
        """Enhance message with context for follow-ups."""
        memory = self.get_memory()
        if not memory:
            return message
        
        if memory.is_follow_up(message):
            resolved = memory.resolve_reference(message)
            context = memory.get_context_summary()
            return f"[Context: {context}] {resolved}"
        
        return message
    
    def clear(self):
        """Clear session memory."""
        if self.MEMORY_KEY in self.session:
            del self.session[self.MEMORY_KEY]
    
    def _save(self, memory: SessionMemory):
        """Save memory to session."""
        self.session[self.MEMORY_KEY] = memory.to_dict()
