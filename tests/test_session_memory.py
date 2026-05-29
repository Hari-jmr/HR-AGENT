"""
Unit tests for Session Memory Service.
"""

import pytest
import time

from backend.services.session_memory import SessionMemory, SessionMemoryManager


class TestSessionMemory:
    """Tests for SessionMemory dataclass."""

    def test_initialization(self):
        memory = SessionMemory(employee_id=123)
        assert memory.employee_id == 123
        assert memory.conversation == []
        assert memory.last_topic is None
        assert memory.last_query_type is None

    def test_add_message(self):
        memory = SessionMemory(employee_id=123)
        memory.add_message('user', 'Hello')
        memory.add_message('assistant', 'Hi there!')
        
        assert len(memory.conversation) == 2
        assert memory.conversation[0]['role'] == 'user'
        assert memory.conversation[1]['role'] == 'assistant'

    def test_message_limit(self):
        memory = SessionMemory(employee_id=123)
        for i in range(35):
            memory.add_message('user', f'Message {i}')
        
        assert len(memory.conversation) == 30
        assert memory.conversation[0]['content'] == 'Message 5'

    def test_set_context(self):
        memory = SessionMemory(employee_id=123)
        memory.set_context('leave_balance', 'leave_balance', 'casual leave')
        
        assert memory.last_topic == 'leave_balance'
        assert memory.last_query_type == 'leave_balance'
        assert memory.last_entity == 'casual leave'

    def test_get_context_summary(self):
        memory = SessionMemory(employee_id=123)
        assert memory.get_context_summary() == 'new conversation'
        
        memory.set_context('salary', 'salary', 'monthly pay')
        assert 'salary' in memory.get_context_summary()

    def test_get_recent_messages(self):
        memory = SessionMemory(employee_id=123)
        for i in range(10):
            memory.add_message('user' if i % 2 == 0 else 'assistant', f'Msg {i}')
        
        recent = memory.get_recent_messages(4)
        assert len(recent) == 4
        assert recent[-1]['content'] == 'Msg 9'

    def test_is_follow_up(self):
        memory = SessionMemory(employee_id=123)
        assert memory.is_follow_up('what about my salary?') == True
        assert memory.is_follow_up('How about casual leaves?') == True
        assert memory.is_follow_up('and my attendance?') == True
        assert memory.is_follow_up('Show me my payslip') == True
        assert memory.is_follow_up('I want my leave balance') == False

    def test_resolve_reference(self):
        memory = SessionMemory(employee_id=123)
        memory.last_entity = 'casual leave'
        
        result = memory.resolve_reference('what about it?')
        assert result == 'what about casual leave?'
        
        result2 = memory.resolve_reference('show me that')
        assert result2 == 'show me casual leave'
        
        result3 = memory.resolve_reference('tell me about leaves')
        assert result3 == 'tell me about leaves'

    def test_serialize_deserialize(self):
        memory = SessionMemory(employee_id=123, employee_name='John Doe')
        memory.add_message('user', 'Hello')
        memory.set_context('salary', 'salary')
        
        data = memory.to_dict()
        restored = SessionMemory.from_dict(data)
        
        assert restored.employee_id == 123
        assert restored.employee_name == 'John Doe'
        assert len(restored.conversation) == 1
        assert restored.last_topic == 'salary'


class TestSessionMemoryManager:
    """Tests for SessionMemoryManager."""

    def test_initialize(self):
        session = {}
        manager = SessionMemoryManager(session)
        
        employee_info = {'employee_id': 456, 'name': 'Jane', 'emp_code': 'EMP001'}
        memory = manager.initialize(employee_info)
        
        assert memory.employee_id == 456
        assert 'session_memory' in session

    def test_get_or_create(self):
        session = {}
        manager = SessionMemoryManager(session)
        
        employee_info = {'employee_id': 789, 'name': 'Bob', 'emp_code': 'EMP002'}
        memory1 = manager.get_or_create(employee_info)
        memory2 = manager.get_or_create(employee_info)
        
        assert memory1.employee_id == memory2.employee_id

    def test_add_messages(self):
        session = {}
        manager = SessionMemoryManager(session)
        
        employee_info = {'employee_id': 100, 'name': 'Test', 'emp_code': 'EMP003'}
        manager.initialize(employee_info)
        
        manager.add_user_message('Hello')
        manager.add_assistant_message('Hi!')
        
        memory = manager.get_memory()
        assert len(memory.conversation) == 2

    def test_enhance_message(self):
        session = {}
        manager = SessionMemoryManager(session)
        
        employee_info = {'employee_id': 101, 'name': 'Test', 'emp_code': 'EMP004'}
        manager.initialize(employee_info)
        manager.update_context('salary', 'salary', 'monthly pay')
        
        enhanced = manager.enhance_message('what about it?')
        assert 'Context' in enhanced

    def test_clear(self):
        session = {}
        manager = SessionMemoryManager(session)
        
        employee_info = {'employee_id': 102, 'name': 'Test', 'emp_code': 'EMP005'}
        manager.initialize(employee_info)
        manager.add_user_message('Test message')
        
        manager.clear()
        
        assert manager.get_memory() is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
