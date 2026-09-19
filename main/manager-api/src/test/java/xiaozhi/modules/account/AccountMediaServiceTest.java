package xiaozhi.modules.account;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.nio.file.Path;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;

import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.account.service.AccountMediaService;

class AccountMediaServiceTest {
    @TempDir Path temp;

    @Test void imageUploadPersistsOwnedMetadata() {
        AccountRepository repository = mock(AccountRepository.class);
        AccountMediaService service = new AccountMediaService(repository);
        ReflectionTestUtils.setField(service, "mediaDir", temp.toString());
        var file = new MockMultipartFile("file", "avatar.png", "image/png", new byte[]{1,2,3});
        var result = service.upload(8L, "AVATAR", file);
        assertEquals("IMAGE", result.get("mediaType"));
        verify(repository).createMedia(anyString(), eq(8L), eq("IMAGE"), eq("AVATAR"),
                anyString(), eq("avatar.png"), eq("image/png"), eq(3L), anyString());
    }

    @Test void executableContentAndForeignAssetAreRejected() {
        AccountRepository repository = mock(AccountRepository.class);
        AccountMediaService service = new AccountMediaService(repository);
        ReflectionTestUtils.setField(service, "mediaDir", temp.toString());
        var executable = new MockMultipartFile("file", "bad.exe", "application/octet-stream", new byte[]{1});
        assertEquals(ErrorCode.MEDIA_ASSET_INVALID,
                assertThrows(RenException.class, () -> service.upload(8L, "ATTACHMENT", executable)).getCode());
        when(repository.media(8L, "foreign")).thenReturn(Optional.empty());
        assertEquals(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION,
                assertThrows(RenException.class, () -> service.download(8L, "foreign")).getCode());
    }
}
