package com.mailocr.api.controller;

import com.mailocr.api.model.Shipment;
import com.mailocr.api.service.ShipmentService;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/shipments")
public class ShipmentController {
  private final ShipmentService shipmentService;

  public ShipmentController(ShipmentService shipmentService) {
    this.shipmentService = shipmentService;
  }

  @PostMapping(value = "/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
  public ShipmentService.ExtractionResponse extract(
      @RequestParam("file") @NotNull MultipartFile file,
      @RequestParam(value = "ocrBackend", required = false) String ocrBackend
  ) {
    return shipmentService.extract(file, ocrBackend);
  }

  @GetMapping
  public List<Shipment> recent() {
    return shipmentService.recent();
  }

  @GetMapping("/review")
  public List<Shipment> reviewQueue() {
    return shipmentService.reviewQueue();
  }

  @PutMapping("/{id}/review")
  public Shipment submitReview(@PathVariable String id, @RequestBody ReviewRequest request) {
    return shipmentService.submitReview(id, request.fields(), request.reviewedBy());
  }

  @GetMapping(value = "/{id}/image", produces = MediaType.IMAGE_JPEG_VALUE)
  public Resource image(@PathVariable String id) {
    return shipmentService.image(id);
  }

  @PostMapping("/{id}/export")
  public ShipmentService.ExportResponse export(@PathVariable String id, @RequestBody ExportRequest request) {
    return shipmentService.export(id, request.sheet(), request.email());
  }

  @PostMapping("/export-all")
  public ShipmentService.ExportAllResponse exportAll() {
    return shipmentService.exportAllToSheet();
  }

  @PostMapping("/{id}/storage")
  public ShipmentService.StorageResponse storeJson(@PathVariable String id) {
    return shipmentService.storeJson(id);
  }

  public record ReviewRequest(Map<String, Object> fields, String reviewedBy) {
  }

  public record ExportRequest(boolean sheet, boolean email) {
  }
}
