@Echo off
;%~dp0\JLink\JLink -if swd -commandFile %~dp0\program_net.jlink
;%~dp0\JLink\JLink -if swd -commandFile %~dp0\program_app.jlink
%~dp0\JLink\JLink -if swd -commandFile %~dp0\program_test.jlink

pause