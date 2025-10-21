-- PostgreSQL용 테이블 구조

-- 그룹 테이블
CREATE TABLE IF NOT EXISTS groups (
    group_id UUID PRIMARY KEY,
    group_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 이벤트 테이블
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY,
    group_id UUID NOT NULL,
    source_product VARCHAR(255),
    source_ip INET,
    user_agent TEXT,
    occurred_at TIMESTAMPTZ,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(group_id)
);

-- CloudTrail 로그 테이블
CREATE TABLE IF NOT EXISTS cloudtrail (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL,
    event_time TIMESTAMP NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    event_source VARCHAR(255) NOT NULL,
    aws_region VARCHAR(50) NOT NULL,
    source_ip INET,
    user_identity JSONB,
    request_parameters JSONB,
    response_elements JSONB,
    cloudtrail_event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100),
    management_event BOOLEAN,
    recipient_account_id VARCHAR(20),
    event_category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE INDEX idx_cloudtrail_event_time ON cloudtrail (event_time);
CREATE INDEX idx_cloudtrail_event_name ON cloudtrail (event_name);
CREATE INDEX idx_cloudtrail_event_id ON cloudtrail (cloudtrail_event_id);
CREATE INDEX idx_cloudtrail_user_identity ON cloudtrail USING GIN (user_identity);
CREATE INDEX idx_events_group_id ON events (group_id);
CREATE INDEX idx_cloudtrail_event_id_fk ON cloudtrail (event_id);