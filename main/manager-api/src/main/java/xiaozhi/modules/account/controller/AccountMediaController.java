package xiaozhi.modules.account.controller;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.account.service.AccountMediaService;
import xiaozhi.modules.security.user.SecurityUser;

@RestController
@RequestMapping("/account/media")
@RequiredArgsConstructor
public class AccountMediaController {
    private final AccountMediaService service;
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Result<Map<String,Object>> upload(@RequestParam String purpose, @RequestPart MultipartFile file) {
        return new Result<Map<String,Object>>().ok(service.upload(SecurityUser.getUserId(), purpose, file));
    }
    @GetMapping("/{assetId}/content") public ResponseEntity<org.springframework.core.io.Resource> download(@PathVariable String assetId) {
        var d = service.download(SecurityUser.getUserId(), assetId);
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(d.contentType()))
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.inline().filename(d.filename(), StandardCharsets.UTF_8).build().toString())
                .body(d.resource());
    }
    @DeleteMapping("/{assetId}") public Result<Void> delete(@PathVariable String assetId) {
        service.delete(SecurityUser.getUserId(), assetId); return new Result<>();
    }
}
