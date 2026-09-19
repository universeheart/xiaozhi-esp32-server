package xiaozhi.modules.account.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.account.repository.AccountRepository;

@Service
@RequiredArgsConstructor
public class AccountMediaService {
    private final AccountRepository repository;
    @Value("${account.media-dir:uploadfile/account}") private String mediaDir;

    public Map<String, Object> upload(long accountId, String purpose, MultipartFile file) {
        if (file == null || file.isEmpty()) throw new RenException(ErrorCode.UPLOAD_FILE_EMPTY);
        String contentType = file.getContentType() == null ? "application/octet-stream" : file.getContentType().toLowerCase(Locale.ROOT);
        String mediaType = contentType.startsWith("image/") ? "IMAGE" : contentType.startsWith("audio/") ? "AUDIO" :
                contentType.startsWith("video/") ? "VIDEO" : null;
        if (mediaType == null) throw new RenException(ErrorCode.MEDIA_ASSET_INVALID);
        long max = "IMAGE".equals(mediaType) ? 20L * 1024 * 1024 : "AUDIO".equals(mediaType) ? 50L * 1024 * 1024 : 200L * 1024 * 1024;
        if (file.getSize() > max) throw new RenException(ErrorCode.FILE_SIZE_OVER_LIMIT);
        String id = UUID.randomUUID().toString();
        String suffix = safeSuffix(file.getOriginalFilename());
        String objectKey = accountId + "/" + id + suffix;
        Path root = Paths.get(mediaDir).toAbsolutePath().normalize();
        Path target = root.resolve(objectKey).normalize();
        if (!target.startsWith(root)) throw new RenException(ErrorCode.MEDIA_ASSET_INVALID);
        try {
            Files.createDirectories(target.getParent());
            try (InputStream in = file.getInputStream()) { Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING); }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(target)) {
                byte[] buffer = new byte[8192];
                for (int read; (read = in.read(buffer)) >= 0;) digest.update(buffer, 0, read);
            }
            String sha256 = HexFormat.of().formatHex(digest.digest());
            repository.createMedia(id, accountId, mediaType, normalizePurpose(purpose), objectKey,
                    file.getOriginalFilename(), contentType, file.getSize(), sha256);
            return Map.of("assetId", id, "mediaType", mediaType, "contentType", contentType,
                    "sizeBytes", file.getSize(), "sha256", sha256);
        } catch (Exception e) {
            try { Files.deleteIfExists(target); } catch (IOException ignored) { }
            throw new RenException(ErrorCode.UPLOAD_FILE_ERROR, e);
        }
    }

    public Download download(long accountId, String assetId) {
        Map<String, Object> row = repository.media(accountId, assetId)
                .orElseThrow(() -> new RenException(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION));
        Path root = Paths.get(mediaDir).toAbsolutePath().normalize();
        Path path = root.resolve(String.valueOf(row.get("object_key"))).normalize();
        if (!path.startsWith(root) || !Files.isRegularFile(path)) throw new RenException(ErrorCode.MEDIA_ASSET_INVALID);
        try { return new Download(new UrlResource(path.toUri()), String.valueOf(row.get("content_type")),
                String.valueOf(row.get("original_filename"))); }
        catch (Exception e) { throw new RenException(ErrorCode.RESOURCE_READ_ERROR, e); }
    }

    public void delete(long accountId, String assetId) {
        Map<String, Object> row = repository.media(accountId, assetId)
                .orElseThrow(() -> new RenException(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION));
        if (repository.deleteMedia(accountId, assetId) != 1) throw new RenException(ErrorCode.MEDIA_ASSET_INVALID);
        Path root = Paths.get(mediaDir).toAbsolutePath().normalize();
        Path path = root.resolve(String.valueOf(row.get("object_key"))).normalize();
        if (path.startsWith(root)) try { Files.deleteIfExists(path); } catch (IOException ignored) { }
    }

    private static String safeSuffix(String name) {
        if (name == null) return "";
        int dot = name.lastIndexOf('.');
        String s = dot < 0 ? "" : name.substring(dot).toLowerCase(Locale.ROOT);
        return s.matches("\\.[a-z0-9]{1,8}") ? s : "";
    }
    private static String normalizePurpose(String p) {
        String value = p == null ? "ATTACHMENT" : p.trim().toUpperCase(Locale.ROOT);
        if (!value.matches("AVATAR|VOICE_SAMPLE|VOICE_MODEL|PATROL_VIDEO|MEMORY_MEDIA|EXPORT|ATTACHMENT"))
            throw new RenException(ErrorCode.MEDIA_ASSET_INVALID);
        return value;
    }
    public record Download(Resource resource, String contentType, String filename) {}
}
