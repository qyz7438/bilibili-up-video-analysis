from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Up(Base):
    __tablename__ = "ups"

    id = Column(Integer, primary_key=True, index=True)
    uid = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    face = Column(String)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    videos = relationship("Video", back_populates="up", cascade="all, delete-orphan")


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    bvid = Column(String, unique=True, index=True, nullable=False)
    aid = Column(String)
    title = Column(String)
    description = Column(Text)
    pic = Column(String)
    pubdate = Column(DateTime(timezone=True))
    up_id = Column(Integer, ForeignKey("ups.id"), nullable=False)
    subtitle_content = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    up = relationship("Up", back_populates="videos")
    analysis = relationship("Analysis", back_populates="video", uselist=False, cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True, nullable=False)
    summary = Column(Text)
    key_points = Column(Text)
    topics = Column(Text)
    sentiment = Column(String)
    llm_model = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("Video", back_populates="analysis")


class FavoriteVideo(Base):
    __tablename__ = "favorite_videos"

    id = Column(Integer, primary_key=True, index=True)
    bvid = Column(String, index=True, nullable=False)
    title = Column(String)
    cover = Column(String)
    intro = Column(Text)
    duration = Column(Integer)
    uploader_name = Column(String)
    uploader_mid = Column(String)
    fav_time = Column(DateTime(timezone=True))
    pubtime = Column(DateTime(timezone=True))
    subtitle_content = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    analysis = relationship("FavoriteAnalysis", back_populates="video", uselist=False, cascade="all, delete-orphan")


class FavoriteAnalysis(Base):
    __tablename__ = "favorite_analyses"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("favorite_videos.id"), unique=True, nullable=False)
    summary = Column(Text)
    key_points = Column(Text)
    topics = Column(Text)
    sentiment = Column(String)
    llm_model = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("FavoriteVideo", back_populates="analysis")
