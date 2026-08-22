package xiaozhi.modules.member.controller;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.member.dto.MemberProfileUpsertDTO;
import xiaozhi.modules.member.service.MemberProfileService;

@RestController
@RequestMapping("/memory/profile")
@RequiredArgsConstructor
public class MemberProfileController {
    private final MemberProfileService memberProfileService;

    @PostMapping("/upsert")
    public Result<Boolean> upsert(@Valid @RequestBody MemberProfileUpsertDTO dto) {
        return new Result<Boolean>().ok(memberProfileService.upsert(dto));
    }
}
