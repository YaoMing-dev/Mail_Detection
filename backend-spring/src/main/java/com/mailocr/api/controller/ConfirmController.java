package com.mailocr.api.controller;

import com.mailocr.api.service.PipelineService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ConfirmController {
  private final PipelineService pipelineService;

  public ConfirmController(PipelineService pipelineService) {
    this.pipelineService = pipelineService;
  }

  @GetMapping(value = "/confirm-received", produces = MediaType.TEXT_HTML_VALUE)
  public String confirmReceived(@RequestParam("id") String trackingId) {
    pipelineService.confirmReceived(trackingId);
    String escapedTrackingId = escapeHtml(trackingId);
    return """
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>Received</title>
        </head>
        <body style="font-family:Arial,sans-serif;text-align:center;padding:60px;color:#1f2937">
          <h2 style="color:#15803d">Da xac nhan nhan buu pham</h2>
          <p>Ma van don: <strong>%s</strong></p>
          <p>Trang thai da duoc cap nhat thanh <strong>Received</strong>.</p>
        </body>
        </html>
        """.formatted(escapedTrackingId);
  }

  private static String escapeHtml(String value) {
    return value == null ? "" : value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
        .replace("'", "&#39;");
  }
}
