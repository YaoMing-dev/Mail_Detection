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
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DataAccessException;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class ShipmentService {
  private static final int MIN_TRAINING_REVIEWS = 20;

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
    Shipment saved = shipmentRepository.save(shipment);
    storeSnapshot(saved);
    return saved;
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
    return storeSnapshot(shipment);
  }

  private synchronized StorageResponse storeSnapshot(Shipment shipment) {
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

  public StorageCatalogResponse storageCatalog() {
    Map<String, List<Map<String, Object>>> storage = readStorage();
    List<StorageImageResponse> images = new ArrayList<>();
    int totalReviews = 0;

    for (Map.Entry<String, List<Map<String, Object>>> entry : storage.entrySet()) {
      List<Map<String, Object>> snapshots = entry.getValue() == null ? List.of() : entry.getValue();
      totalReviews += snapshots.size();
      Map<String, Object> latest = snapshots.isEmpty() ? new LinkedHashMap<>() : snapshots.get(snapshots.size() - 1);
      images.add(new StorageImageResponse(
          entry.getKey(),
          snapshots.size(),
          stringValue(latest.get("shipmentId")),
          stringValue(latest.get("previewImagePath")),
          stringValue(latest.get("savedAt")),
          mapValue(latest.get("fields"))
      ));
    }

    return new StorageCatalogResponse(
        projectRoot().resolve("storage.json").normalize().toString(),
        images.size(),
        totalReviews,
        images
    );
  }

  public TrainingStatusResponse trainingStatus() {
    StorageCatalogResponse catalog = storageCatalog();
    int missing = Math.max(0, MIN_TRAINING_REVIEWS - catalog.totalReviews());
    return new TrainingStatusResponse(
        catalog.totalReviews(),
        MIN_TRAINING_REVIEWS,
        missing,
        missing == 0,
        "Training requires at least 20 reviewed storage snapshots. After training is approved, the old model will be replaced by the new model and the app will use the new model immediately.",
        properties.getModelPath()
    );
  }

  public synchronized TrainingStartResponse startTraining(boolean confirmed) {
    TrainingStatusResponse status = trainingStatus();
    if (!confirmed) {
      throw new IllegalArgumentException("Training confirmation is required.");
    }
    if (!status.canTrain()) {
      throw new IllegalArgumentException("Not enough reviewed data. Need " + status.missingReviews() + " more review snapshots before training.");
    }

    Path projectRoot = projectRoot();
    Path trainingDir = projectRoot.resolve("training_runs").normalize();
    try {
      Files.createDirectories(trainingDir);
      String requestId = "training-" + Instant.now().toString().replace(":", "").replace(".", "");
      Path manifest = trainingDir.resolve(requestId + ".json");
      Map<String, Object> payload = new LinkedHashMap<>();
      payload.put("requestId", requestId);
      payload.put("requestedAt", Instant.now());
      payload.put("reviewCount", status.reviewCount());
      payload.put("storagePath", projectRoot.resolve("storage.json").normalize().toString());
      payload.put("currentModelPath", properties.getModelPath());
      payload.put("replacementPolicy", "Replace old model with newly trained model after training completes.");
      payload.put("status", "REQUESTED");
      objectMapper.writerWithDefaultPrettyPrinter().writeValue(manifest.toFile(), payload);
      return new TrainingStartResponse(
          true,
          requestId,
          manifest.toString(),
          "Training request created. The next training runner should consume this manifest, train from reviewed data, replace the old model, and apply the new model."
      );
    } catch (IOException e) {
      throw new PipelineException("Cannot write training request manifest.", e);
    }
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

  private Map<String, List<Map<String, Object>>> readStorage() {
    Path storagePath = projectRoot().resolve("storage.json").normalize();
    if (!Files.exists(storagePath)) {
      return new LinkedHashMap<>();
    }
    try {
      return objectMapper.readValue(storagePath.toFile(), new TypeReference<Map<String, List<Map<String, Object>>>>() {});
    } catch (IOException e) {
      throw new PipelineException("Cannot read storage.json.", e);
    }
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

  @SuppressWarnings("unchecked")
  private static Map<String, Object> mapValue(Object value) {
    return value instanceof Map<?, ?> map ? (Map<String, Object>) map : new LinkedHashMap<>();
  }

  private static String stringValue(Object value) {
    return Optional.ofNullable(value).map(String::valueOf).orElse(null);
  }

  public record ExtractionResponse(Shipment shipment, boolean persisted, String pipelineOutput) {
  }

  public record ExportResponse(boolean ok, boolean sheet, boolean email, String output) {
  }

  public record AppConfigResponse(String googleSheetUrl, String storagePath) {
  }

  public record StorageResponse(boolean ok, String imageName, String storagePath, int savedVersions) {
  }

  public record StorageCatalogResponse(String storagePath, int imageCount, int totalReviews, List<StorageImageResponse> images) {
  }

  public record StorageImageResponse(
      String imageName,
      int versions,
      String shipmentId,
      String previewImagePath,
      String savedAt,
      Map<String, Object> fields
  ) {
  }

  public record TrainingStatusResponse(
      int reviewCount,
      int minimumReviews,
      int missingReviews,
      boolean canTrain,
      String reason,
      String activeModelPath
  ) {
  }

  public record TrainingStartResponse(boolean ok, String requestId, String manifestPath, String message) {
  }
}
