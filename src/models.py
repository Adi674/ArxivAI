# ============================================================================
# src/models.py — Complete Database Models (All 13 Tables)
# Consolidated in one file for easier management
# ============================================================================

from sqlalchemy import (
    Column, String, UUID, Boolean, DateTime, Integer, Float, 
    ARRAY, JSON, ForeignKey, Text, Numeric, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from datetime import datetime

from src.database import Base


# ============================================================================
# USER & AUTHENTICATION
# ============================================================================

class User(Base):
    """User accounts and profiles"""
    
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    domains = Column(ARRAY(String), default=[], nullable=False)
    organization = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    papers = relationship("Paper", back_populates="user", cascade="all, delete-orphan")
    collaborations = relationship("Collaboration", back_populates="creator", cascade="all, delete-orphan")
    collaboration_members = relationship("CollaborationMember", back_populates="user", cascade="all, delete-orphan")
    collaboration_applications = relationship("CollaborationApplication", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    user_memory = relationship("UserMemory", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


# ============================================================================
# PAPERS
# ============================================================================

class Paper(Base):
    """Academic papers (arXiv + user uploads)"""
    
    __tablename__ = "papers"
    
    id = Column(String(50), primary_key=True)  # arXiv ID or custom UUID
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    
    title = Column(String(500), nullable=False)
    authors = Column(Text, nullable=False)
    domain = Column(String(50), nullable=False, index=True)
    
    source = Column(String(20), nullable=False, index=True)  # 'arxiv' | 'user_uploaded' | 'arxiv_fetched'
    visibility = Column(String(20), default="private", nullable=False, index=True)  # 'private' | 'collaborative' | 'public'
    
    chroma_ids = Column(ARRAY(String), default=[], nullable=False)  # For Chroma chunk deletion
    
    file_path = Column(String(255), nullable=True)  # S3 key or local path
    pdf_url = Column(Text, nullable=True)  # Original PDF URL
    
    upload_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    citation_count = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete
    
    # Indexes
    Index("idx_papers_user_visibility", "user_id", "visibility")
    Index("idx_papers_domain_source", "domain", "source")
    
    # Relationships
    user = relationship("User", back_populates="papers")
    collaboration_papers = relationship("CollaborationPaper", back_populates="paper", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Paper(id={self.id}, title={self.title})>"


# ============================================================================
# COLLABORATIONS
# ============================================================================

class Collaboration(Base):
    """Collaboration projects (direct invites or group projects)"""
    
    __tablename__ = "collaborations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    type = Column(String(20), nullable=False, index=True)  # 'direct_invite' | 'project'
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    project_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    domains = Column(ARRAY(String), default=[], nullable=False)
    
    status = Column(String(20), default="active", nullable=False, index=True)  # 'active' | 'archived'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    creator = relationship("User", back_populates="collaborations")
    members = relationship("CollaborationMember", back_populates="collaboration", cascade="all, delete-orphan")
    papers = relationship("CollaborationPaper", back_populates="collaboration", cascade="all, delete-orphan")
    applications = relationship("CollaborationApplication", back_populates="collaboration", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Collaboration(id={self.id}, type={self.type})>"


class CollaborationMember(Base):
    """Many-to-many: users in collaborations"""
    
    __tablename__ = "collaboration_members"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collaboration_id = Column(UUID(as_uuid=True), ForeignKey("collaborations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role = Column(String(20), default="member", nullable=False)  # 'creator' | 'member'
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Unique constraint handled in migration
    __table_args__ = (
        Index("idx_collab_members_unique", "collaboration_id", "user_id", unique=True),
    )
    
    # Relationships
    collaboration = relationship("Collaboration", back_populates="members")
    user = relationship("User", back_populates="collaboration_members")
    
    def __repr__(self) -> str:
        return f"<CollaborationMember(collab_id={self.collaboration_id}, user_id={self.user_id})>"


class CollaborationPaper(Base):
    """Many-to-many: papers shared in collaborations"""
    
    __tablename__ = "collaboration_papers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collaboration_id = Column(UUID(as_uuid=True), ForeignKey("collaborations.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id = Column(String(50), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Unique constraint handled in migration
    __table_args__ = (
        Index("idx_collab_papers_unique", "collaboration_id", "paper_id", unique=True),
    )
    
    # Relationships
    collaboration = relationship("Collaboration", back_populates="papers")
    paper = relationship("Paper", back_populates="collaboration_papers")
    
    def __repr__(self) -> str:
        return f"<CollaborationPaper(collab_id={self.collaboration_id}, paper_id={self.paper_id})>"


class CollaborationApplication(Base):
    """Applications to join project-type collaborations"""
    
    __tablename__ = "collaboration_applications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collaboration_id = Column(UUID(as_uuid=True), ForeignKey("collaborations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    status = Column(String(20), default="pending", nullable=False, index=True)  # 'pending' | 'approved' | 'rejected'
    interest_note = Column(Text, nullable=True)
    
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Unique constraint handled in migration
    __table_args__ = (
        Index("idx_collab_apps_unique", "collaboration_id", "user_id", unique=True),
    )
    
    # Relationships
    collaboration = relationship("Collaboration", back_populates="applications")
    user = relationship("User", back_populates="collaboration_applications")
    
    def __repr__(self) -> str:
        return f"<CollaborationApplication(user_id={self.user_id}, status={self.status})>"


# ============================================================================
# CONVERSATIONS & MESSAGES (CHAT HISTORY)
# ============================================================================

class Conversation(Base):
    """Chat conversations"""
    
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    domain = Column(String(50), nullable=True, index=True)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    is_public = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    context = relationship("ConversationContext", back_populates="conversation", uselist=False, cascade="all, delete-orphan")
    settings = relationship("ConversationSettings", back_populates="conversation", uselist=False, cascade="all, delete-orphan")
    session_states = relationship("SessionState", back_populates="conversation", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"


class Message(Base):
    """Individual messages in conversations"""
    
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role = Column(String(20), nullable=False)  # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    
    query_type = Column(String(50), nullable=True)  # 'single_hop' | 'multi_hop' | 'clarification'
    detected_domain = Column(String(50), nullable=True)
    papers_referenced = Column(ARRAY(String), default=[], nullable=False)
    
    llm_model = Column(String(100), nullable=True)
    llm_tokens_used = Column(Integer, nullable=True)
    llm_cost = Column(Numeric(10, 6), nullable=True)
    
    quality_score = Column(Float, nullable=True)
    ragas_scores = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Indexes
    Index("idx_messages_conversation_created", "conversation_id", "created_at")
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    user = relationship("User", back_populates="messages")
    session_states = relationship("SessionState", back_populates="message")
    
    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"


class ConversationContext(Base):
    """Running context/memory of a conversation"""
    
    __tablename__ = "conversation_context"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    primary_domain = Column(String(50), nullable=True)
    secondary_domains = Column(ARRAY(String), default=[], nullable=False)
    
    papers_referenced = Column(ARRAY(String), default=[], nullable=False)
    papers_searched_count = Column(Integer, default=0, nullable=False)
    
    key_findings = Column(JSON, default={}, nullable=False)
    contradictions_found = Column(JSON, default=[], nullable=False)
    agreements_found = Column(JSON, default=[], nullable=False)
    open_questions = Column(ARRAY(Text), default=[], nullable=False)
    
    turns_count = Column(Integer, default=0, nullable=False)
    reformulations_count = Column(Integer, default=0, nullable=False)
    papers_citations_count = Column(Integer, default=0, nullable=False)
    
    user_clarifications = Column(ARRAY(Text), default=[], nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="context")
    
    def __repr__(self) -> str:
        return f"<ConversationContext(conversation_id={self.conversation_id})>"


class SessionState(Base):
    """Persistent LangGraph agent state for debugging/reproducibility"""
    
    __tablename__ = "session_state"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Query & domain info
    original_query = Column(Text, nullable=False)
    primary_domain = Column(String(50), nullable=True)
    secondary_domains = Column(ARRAY(String), default=[], nullable=False)
    domain_confidence = Column(Float, nullable=True)
    
    # Query analysis
    query_type = Column(String(20), nullable=True)
    sub_queries = Column(ARRAY(Text), default=[], nullable=False)
    needs_personal_papers = Column(Boolean, default=False)
    needs_recent = Column(Boolean, default=False)
    
    # Search strategy
    search_spaces = Column(ARRAY(String), default=[], nullable=False)
    fetch_arxiv_fresh = Column(Boolean, default=False)
    
    # Retrieval
    retrieved_papers = Column(JSON, default={}, nullable=False)
    reformulation_count = Column(Integer, default=0)
    
    # Reasoning
    findings = Column(JSON, default={}, nullable=False)
    contradictions = Column(JSON, default=[], nullable=False)
    agreements = Column(JSON, default=[], nullable=False)
    citation_graph = Column(JSON, default={}, nullable=False)
    knowledge_gaps = Column(ARRAY(Text), default=[], nullable=False)
    
    # Answer
    draft_answer = Column(Text, nullable=True)
    final_answer = Column(Text, nullable=True)
    
    # Evaluation
    hallucination_detected = Column(Boolean, default=False)
    quality_score = Column(Float, nullable=True)
    ragas_scores = Column(JSON, nullable=True)
    needs_refinement = Column(Boolean, default=False)
    refinement_count = Column(Integer, default=0)
    
    # Metadata
    sources = Column(JSON, default=[], nullable=False)
    reasoning_trace = Column(ARRAY(Text), default=[], nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="session_states")
    message = relationship("Message", back_populates="session_states")
    
    def __repr__(self) -> str:
        return f"<SessionState(conversation_id={self.conversation_id}, message_id={self.message_id})>"


class ConversationSettings(Base):
    """Per-conversation settings and preferences"""
    
    __tablename__ = "conversation_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    auto_cite_papers = Column(Boolean, default=True, nullable=False)
    include_confidence_scores = Column(Boolean, default=True, nullable=False)
    include_knowledge_gaps = Column(Boolean, default=True, nullable=False)
    
    papers_limit = Column(Integer, default=10, nullable=False)
    reformulation_attempts = Column(Integer, default=2, nullable=False)
    include_arxiv_fresh = Column(Boolean, default=True, nullable=False)
    
    response_format = Column(String(50), default="paragraph", nullable=False)  # 'paragraph' | 'bullet_points' | 'qa'
    include_citations = Column(Boolean, default=True, nullable=False)
    
    timeout_seconds = Column(Integer, default=60, nullable=False)
    use_cache = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="settings")
    
    def __repr__(self) -> str:
        return f"<ConversationSettings(conversation_id={self.conversation_id})>"


class UserMemory(Base):
    """Persistent user preferences and patterns across conversations"""
    
    __tablename__ = "user_memory"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    preferred_domains = Column(ARRAY(String), default=[], nullable=False)
    preferred_llm_mode = Column(String(20), nullable=True)  # 'budget' | 'balanced' | 'quality' | 'research'
    preferred_response_format = Column(String(50), nullable=True)  # 'paragraph' | 'bullet_points' | 'qa'
    
    frequent_topics = Column(ARRAY(String), default=[], nullable=False)
    frequently_cited_papers = Column(ARRAY(String), default=[], nullable=False)
    
    total_conversations = Column(Integer, default=0, nullable=False)
    total_messages = Column(Integer, default=0, nullable=False)
    average_conversation_length = Column(Integer, default=0, nullable=False)
    most_active_domain = Column(String(50), nullable=True)
    
    quality_score_average = Column(Float, nullable=True)
    
    last_domains_explored = Column(ARRAY(String), default=[], nullable=False)
    last_papers_discussed = Column(ARRAY(String), default=[], nullable=False)
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="user_memory")
    
    def __repr__(self) -> str:
        return f"<UserMemory(user_id={self.user_id})>"