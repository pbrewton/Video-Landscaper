; Based on NSIS's Examples\install-per-user.nsi.
; Keep this script in the installer folder under the project root.
; Compile with NSIS to create dist\VideoLandscaper-Setup.exe.

!define NAME "Video Landscaper"
!define SHORTCUT_NAME "${NAME}"
!define APP_ID "VideoLandscaper"

!define GUI_EXE "${APP_ID}-gui.exe"
!define CLI_EXE "${APP_ID}-cli.exe"
!define APP_DIR "${__FILEDIR__}\..\dist\${APP_ID}"
!define REGPATH_UNINSTSUBKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

!include LogicLib.nsh
!include WinCore.nsh
!include MUI2.nsh

!if /FILEEXISTS "${APP_DIR}\${GUI_EXE}"
!else
  !error "Build the PyInstaller onedir app first: ${APP_DIR}\${GUI_EXE} was not found."
!endif
!if /FILEEXISTS "${APP_DIR}\${CLI_EXE}"
!else
  !error "Build the PyInstaller onedir app first: ${APP_DIR}\${CLI_EXE} was not found."
!endif

; The payload versions originate in pyproject.toml. Read the built executables
; rather than keeping a second app-version constant in this installer script.
; Without /noerrors, missing version resources stop compilation.
!getdllversion "${APP_DIR}\${GUI_EXE}" GUI_VERSION_
!getdllversion "${APP_DIR}\${CLI_EXE}" CLI_VERSION_
!define FILE_VERSION "${GUI_VERSION_1}.${GUI_VERSION_2}.${GUI_VERSION_3}.${GUI_VERSION_4}"
!define CLI_FILE_VERSION "${CLI_VERSION_1}.${CLI_VERSION_2}.${CLI_VERSION_3}.${CLI_VERSION_4}"
!if "${FILE_VERSION}" != "${CLI_FILE_VERSION}"
  !error "GUI and CLI versions differ (${FILE_VERSION} vs ${CLI_FILE_VERSION}). Rebuild both executables before packaging."
!endif
!if ${GUI_VERSION_4} != 0
  !error "Expected a three-component app version with a zero fourth file-version component. Rebuild the app from pyproject.toml."
!endif
!define APP_VERSION "${GUI_VERSION_1}.${GUI_VERSION_2}.${GUI_VERSION_3}"

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

VIProductVersion "${FILE_VERSION}"
VIFileVersion "${FILE_VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName" "${NAME}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion" "${FILE_VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription" "${NAME} Setup"
VIAddVersionKey /LANG=${LANG_ENGLISH} "OriginalFilename" "${APP_ID}-Setup.exe"
VIAddVersionKey /LANG=${LANG_ENGLISH} "LegalCopyright" "Copyright (c) 2026 Video Landscaper contributors"

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
  ; The new GUI/CLI pair replaces the old app-owned executable on upgrade.
  Delete "$InstDir\${APP_ID}.exe"

  CreateShortcut "$SMPrograms\${SHORTCUT_NAME}.lnk" "$InstDir\${GUI_EXE}"

  WriteUninstaller "$InstDir\Uninstall.exe"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "DisplayName" "${NAME}"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "DisplayIcon" "$InstDir\${GUI_EXE},0"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "InstallLocation" "$InstDir"
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "UninstallString" '"$InstDir\Uninstall.exe"'
  WriteRegStr HKCU "${REGPATH_UNINSTSUBKEY}" "QuietUninstallString" '"$InstDir\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${REGPATH_UNINSTSUBKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGPATH_UNINSTSUBKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$SMPrograms\${SHORTCUT_NAME}.lnk"
  ; Remove only the known app payload, not the entire install directory tree.
  Delete "$InstDir\${GUI_EXE}"
  Delete "$InstDir\${CLI_EXE}"
  ; Also remove the previous single-executable payload after an upgrade.
  Delete "$InstDir\${APP_ID}.exe"
  RMDir /r "$InstDir\_internal"
  Delete "$InstDir\Uninstall.exe"
  RMDir "$InstDir"
  DeleteRegKey HKCU "${REGPATH_UNINSTSUBKEY}"
SectionEnd
