package com.mailocr.api.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mailocr.api.config.MailOcrProperties;
import com.mailocr.api.model.Shipment;
import com.mailocr.api.model.ShipmentStatus;
import com.mailocr.api.repository.ShipmentRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
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
  private final ObjectMapper objectMapper;

  public ShipmentService(
      MailOcrProperties properties,
      PipelineService pipelineService,
      ShipmentRepository shipmentRepository,
      ObjectMapper objectMapper
  ) {
    this.properties = properties;
    this.pipelineService = pipelineService;
    this.shipmentRepository = shipmentRepository;
    this.objectMapper = objectMapper;
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

  public AppConfigResponse appConfig() {
    String sheetId = readConfigValue("GOOGLE_SHEET_ID");
    String sheetUrl = sheetId == null || sheetId.isBlank()
        ? null
        : "https://docs.google.com/spreadsheets/d/" + sheetId.trim() + "/edit";
    Path storagePath = projectRoot().resolve("storage.json").normalize();
    return new AppConfigResponse(sheetUrl, storagePath.toString());
  }

  public synchronized StorageResponse storeJson(String id) {
    Shipment shipment = shipmentRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Shipment not found: " + id));
    Path storagePath = projectRoot().resolve("storage.json").normalize();

    Map<String, List<Map<String, Object>>> storage = new LinkedHashMap<>();
    if (Files.exists(storagePath)) {
      try {
        storage = objectMapper.readValue(storagePath.toFile(), new TypeReference<Map<String, List<Map<String, Object>>>>() {});
      } catch (IOException e) {
        throw new PipelineException("Cannot read storage.json.", e);
      }
    }

    String imageName = shipment.getOriginalFilename() == null || shipment.getOriginalFilename().isBlank()
        ? shipment.getId()
        : shipment.getOriginalFilename();

    Map<String, Object> snapshot = new LinkedHashMap<>();
    snapshot.put("shipmentId", shipment.getId());
    snapshot.put("originalFilename", shipment.getOriginalFilename());
    snapshot.put("storedImagePath", shipment.getStoredImagePath());
    snapshot.put("previewImagePath", shipment.getPreviewImagePath());
    snapshot.put("status", shipment.getStatus());
    snapshot.put("needReview", shipment.isNeedReview());
    snapshot.put("fields", shipment.getFields());
    snapshot.put("createdAt", shipment.getCreatedAt());
    snapshot.put("updatedAt", shipment.getUpdatedAt());
    snapshot.put("savedAt", Instant.now());

    storage.computeIfAbsent(imageName, ignored -> new ArrayList<>()).add(snapshot);
    try {
      objectMapper.writerWithDefaultPrettyPrinter().writeValue(storagePath.toFile(), storage);
    } catch (IOException e) {
      throw new PipelineException("Cannot write storage.json.", e);
    }
    return new StorageResponse(true, imageName, storagePath.toString(), storage.get(imageName).size());
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
    Path projectRoot = projectRoot();
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
      Path projectRoot = projectRoot();
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

  private Path projectRoot() {
    return Path.of(properties.getProjectRoot()).toAbsolutePath().normalize();
  }

  private String readConfigValue(String key) {
    String value = System.getenv(key);
    if (value != null && !value.isBlank()) {
      return stripQuotes(value);
    }

    Path envPath = projectRoot().resolve(".env").normalize();
    if (!Files.exists(envPath)) {
      return null;
    }
    try {
      for (String line : Files.readAllLines(envPath)) {
        String trimmed = line.trim();
        if (trimmed.isEmpty() || trimmed.startsWith("#") || !trimmed.contains("=")) {
          continue;
        }
        int idx = trimmed.indexOf('=');
        if (trimmed.substring(0, idx).trim().equals(key)) {
          return stripQuotes(trimmed.substring(idx + 1).trim());
        }
      }
      return null;
    } catch (IOException e) {
      throw new PipelineException("Cannot read .env file.", e);
    }
  }

  private static String stripQuotes(String value) {
    if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
      return value.substring(1, value.length() - 1);
    }
    return value;
  }

  public record ExtractionResponse(Shipment shipment, boolean persisted, String pipelineOutput) {
  }

  public record ExportResponse(boolean ok, boolean sheet, boolean email, String output) {
  }

  public record AppConfigResponse(String googleSheetUrl, String storagePath) {
  }

  public record StorageResponse(boolean ok, String imageName, String storagePath, int savedVersions) {
  }
}
