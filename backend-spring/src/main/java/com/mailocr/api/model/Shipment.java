package com.mailocr.api.model;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "shipments")
public class Shipment {
  @Id
  private String id;
  private String originalFilename;
  private String storedImagePath;
  private String previewImagePath;
  private Map<String, Object> fields = new LinkedHashMap<>();
  private boolean needReview;
  private ShipmentStatus status = ShipmentStatus.PENDING;
  private Instant createdAt = Instant.now();
  private Instant updatedAt = Instant.now();
  private String reviewedBy;

  public String getId() {
    return id;
  }

  public void setId(String id) {
    this.id = id;
  }

  public String getOriginalFilename() {
    return originalFilename;
  }

  public void setOriginalFilename(String originalFilename) {
    this.originalFilename = originalFilename;
  }

  public String getStoredImagePath() {
    return storedImagePath;
  }

  public void setStoredImagePath(String storedImagePath) {
    this.storedImagePath = storedImagePath;
  }

  public String getPreviewImagePath() {
    return previewImagePath;
  }

  public void setPreviewImagePath(String previewImagePath) {
    this.previewImagePath = previewImagePath;
  }

  public Map<String, Object> getFields() {
    return fields;
  }

  public void setFields(Map<String, Object> fields) {
    this.fields = fields;
  }

  public boolean isNeedReview() {
    return needReview;
  }

  public void setNeedReview(boolean needReview) {
    this.needReview = needReview;
  }

  public ShipmentStatus getStatus() {
    return status;
  }

  public void setStatus(ShipmentStatus status) {
    this.status = status;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }

  public String getReviewedBy() {
    return reviewedBy;
  }

  public void setReviewedBy(String reviewedBy) {
    this.reviewedBy = reviewedBy;
  }
}
