package com.example.tts.repository;

import com.example.tts.entity.ContentItem;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ContentItemRepository extends JpaRepository<ContentItem, String> {
    List<ContentItem> findAllByOrderByCreatedAtDesc();
}
