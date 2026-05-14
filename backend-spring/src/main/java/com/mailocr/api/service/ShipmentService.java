package com.mailocr.api.service;

import com.mailocr.api.config.MailOcrProperties;
import com.mailocr.api.model.Shipment;
import com.mailocr.api.model.ShipmentStatus;
import com.mailocr.api.repository.ShipmentRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.DataAccessException;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class ShipmentService {
  private final MailOcrProperties properties;
  private final PipelineService pipelineService;
  private final ShipmentRepository shipmentRepository;

  public ShipmentService(
      MailOcrProperties properties,
      PipelineService pipelineService,
      ShipmentRepository shipmentRepository
  ) {
    this.properties = properties;
    this.pipelineService = pipelineService;
    this.shipmentRepository = shipmentRepository;
  }

  public ExtractionResponse extract(MultipartFile file, String ocrBackend) {
    Path imagePath = storeUpload(file);
    PipelineResult result = pipelineService.extract(imagePath, ocrBackend);

    Shipment shipment = new Shipment();
    shipment.setOriginalFilename(file.getOriginalFilename());
    shipment.setStoredImagePath(imagePath.toString());
    shipment.setPreviewImagePath(result.previewImagePath().toString());
    shipment.setFields(result.fields());
    shipment.setNeedReview(result.needReview());
    shipment.setStatus(result.needReview() ? ShipmentStatus.REVIEW : ShipmentStatus.PENDING);
    shipment.setCreatedAt(Instant.now());
    shipment.setUpdatedAt(Instant.now());

    boolean persisted = true;
    try {
      shipment = shipmentRepository.save(shipment);
    } catch (DataAccessException ex) {
      persisted = false;
    }
    return new ExtractionResponse(shipment, persisted, result.rawOutput());
  }

  public List<Shipment> recent() {
    return shipmentRepository.findTop30ByOrderByCreatedAtDesc();
  }

  public List<Shipment> reviewQueue() {
    return shipmentRepository.findByStatusOrderByCreatedAtDesc(ShipmentStatus.REVIEW);
  }

  public Shipment submitReview(String id, Map<String, Object> fields, String reviewedBy) {
    Shipment shipment = shipmentRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Shipment not found: " + id));
    shipment.setFields(fields);
    shipment.setNeedReview(false);
    shipment.setStatus(ShipmentStatus.VERIFIED);
    shipment.setReviewedBy(reviewedBy);
    shipment.setUpdatedAt(Instant.now());
    return shipmentRepository.save(shipment);
  }

  public Resource image(String id) {
    Shipment shipment = shipmentRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Shipment not found: " + id));
    Path path = resolveImagePath(shipment);
    if (!Files.exists(path)) {
      throw new IllegalArgumentException("Image not found for shipment: " + id);
    }
    return new FileSystemResource(path);
  }

  public ExportResponse export(String id, boolean sendSheet, boolean sendEmail) {
    Shipment shipment = shipmentRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Shipment not found: " + id));
    String output = pipelineService.export(shipment.getFields(), sendSheet, sendEmail);
    return new ExportResponse(true, sendSheet, sendEmail, output);
  }

  private Path storeUpload(MultipartFile file) {
    if (file.isEmpty()) {
      throw new IllegalArgumentException("Upload file is empty.");
    }
    String originalName = file.getOriginalFilename() == null ? "image" : file.getOriginalFilename();
    String ext = "";
    int dot = originalName.lastIndexOf('.');
    if (dot >= 0 && dot < originalName.length() - 1) {
      ext = originalName.substring(dot).replaceAll("[^A-Za-z0-9.]", "");
    }
    Path projectRoot = Path.of(properties.getProjectRoot()).toAbsolutePath().normalize();
    Path uploadDir = projectRoot.resolve(properties.getUploadDir()).normalize();
    try {
      Files.createDirectories(uploadDir);
      Path target = uploadDir.resolve(UUID.randomUUID() + ext).normalize();
      if (!target.startsWith(uploadDir)) {
        throw new IllegalArgumentException("Invalid upload path.");
      }
      file.transferTo(target);
      return target;
    } catch (IOException e) {
      throw new PipelineException("Cannot store uploaded file.", e);
    }
  }

  private Path resolveImagePath(Shipment shipment) {
    if (shipment.getPreviewImagePath() != null) {
      Path preview = Path.of(shipment.getPreviewImagePath()).toAbsolutePath().normalize();
      if (Files.exists(preview)) {
        return preview;
      }
    }

    if (shipment.getStoredImagePath() != null) {
      Path stored = Path.of(shipment.getStoredImagePath()).toAbsolutePath().normalize();
      String fileName = stored.getFileName().toString();
      int dot = fileName.lastIndexOf('.');
      String stem = dot > 0 ? fileName.substring(0, dot) : fileName;
      Path projectRoot = Path.of(properties.getProjectRoot()).toAbsolutePath().normalize();
      Path generatedPreview = projectRoot.resolve(properties.getOutputDir()).resolve(stem + "_preview.jpg").normalize();
      if (Files.exists(generatedPreview)) {
        shipment.setPreviewImagePath(generatedPreview.toString());
        shipmentRepository.save(shipment);
        return generatedPreview;
      }
      return stored;
    }

    throw new IllegalArgumentException("Shipment has no image path: " + shipment.getId());
  }

  public record ExtractionResponse(Shipment shipment, boolean persisted, String pipelineOutput) {
  }

  public record ExportResponse(boolean ok, boolean sheet, boolean email, String output) {
  }
}
