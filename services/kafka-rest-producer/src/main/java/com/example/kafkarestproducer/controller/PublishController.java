package com.example.kafkarestproducer.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PublishController {

    private final KafkaTemplate<String, String> kafkaTemplate;

    private static final String TOPIC = "step1";

    public PublishController(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @PostMapping("/publish")
    public ResponseEntity<String> publish(@RequestBody String payload) {
        kafkaTemplate.send(TOPIC, payload);
        return ResponseEntity.accepted().body("queued");
    }
}


