package com.mailocr.api.controller;

import com.mailocr.api.service.ShipmentService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/app")
public class AppController {
  private final ShipmentService shipmentService;

  public AppController(ShipmentService shipmentService) {
    this.shipmentService = shipmentService;
  }

  @GetMapping("/config")
  public ShipmentService.AppConfigResponse config() {
    return shipmentService.appConfig();
  }
}
