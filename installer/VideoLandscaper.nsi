; Based on NSIS's Examples\install-per-user.nsi.
; Keep this script in the installer folder under the project root.
; Compile with NSIS to create dist\VideoLandscaper-Setup.exe.

!define NAME "Video Landscaper"
!define SHORTCUT_NAME "${NAME}"
!define APP_ID "VideoLandscaper"

!define EXE "${APP_ID}.exe"
!define APP_DIR "${__FILEDIR__}\..\dist\${APP_ID}"
!define REGPATH_UNINSTSUBKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

!include LogicLib.nsh
!include WinCore.nsh
!include MUI2.nsh

!if /FILEEXISTS "${APP_DIR}\${EXE}"
!else
  !error "Build the PyInstaller onedir app first: ${APP_DIR}\${EXE} was not found."
!endif

Name "${NAME}"
OutFile "${__FILEDIR__}\..\dist\${APP_ID}-Setup.exe"
Unicode True
RequestExecutionLevel User
SetCompressor /SOLID lzma

; A previous install's location, or /D=, takes priority over the default.
InstallDir ""
InstallDirRegKey HKCU "${REGPATH_UNINSTSUBKEY}" "InstallLocation"

; Wait for Next on the welcome page before starting the file copy.
; No directory page: the wizard uses the per-user location chosen in .onInit.
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${NAME} Setup"
!define MUI_WELCOMEPAGE_TITLE_3LINES
!define MUI_WELCOMEPAGE_TEXT "This will install the ${NAME} app$\r$\nand create the following Start Menu item:$\r$\n$\r$\n[ ${SHORTCUT_NAME} ]$\r$\n$\r$\nClick Next to begin installation."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"
; The welcome page directly precedes copying, so label its action Next.
InstallButtonText "&Next >"

Function .onInit
  SetShellVarContext Current
  ${If} $InstDir == ""
    GetKnownFolderPath $InstDir ${FOLDERID_UserProgramFiles}
    ${If} $InstDir == ""
      StrCpy $InstDir "$LocalAppData\Programs"
    ${EndIf}
    StrCpy $InstDir "$InstDir\${APP_ID}"
  ${EndIf}
FunctionEnd

Function un.onInit
  SetShellVarContext Current
FunctionEnd

Section "Install"
  SetOutPath "$InstDir"
  SetOverwrite On
  ; Include the entire onedir bundle, preserving _internal and its contents.
  File /r "${APP_DIR}\*"

  CreateShortcut "$SMPrograms\${SHORTCUT_NAME}.lnk" "$InstDir\${EXE}"

  WriteUninstaller "$InstDir\Uninstall.exe"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "DisplayName" "${NAME}"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "DisplayIcon" "$InstDir\${EXE},0"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "InstallLocation" "$InstDir"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "UninstallString" '"$InstDir\Uninstall.exe"'
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "QuietUninstallString" '"$InstDir\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${REGPATH_UNINSTSUBKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGPATH_UNINSTSUBKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$SMPrograms\${SHORTCUT_NAME}.lnk"
  ; Remove only the known app payload, not the entire install directory tree.
  Delete "$InstDir\${EXE}"
  RMDir /r "$InstDir\_internal"
  Delete "$InstDir\Uninstall.exe"
  RMDir "$InstDir"
  DeleteRegKey HKCU "${REGPATH_UNINSTSUBKEY}"
SectionEnd
