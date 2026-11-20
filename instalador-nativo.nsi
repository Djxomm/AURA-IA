Unicode true
!include "MUI2.nsh"
Name "AURA Inteligencia Artificial"
OutFile "entrega\AURA-3.1.0-Nativa-Instalador-Windows-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\AURA"
RequestExecutionLevel user
SetCompressor lzma
SetCompressorDictSize 16
!define MUI_ICON "agente_ia\static\assets\aura.ico"
!define MUI_UNICON "agente_ia\static\assets\aura.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\LEEME.txt"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LEEME-NATIVA.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"
Section "AURA Inteligencia Artificial"
 SetOutPath "$INSTDIR"
 File /r /x modelos /x voz "dist\AURA-Nativa\*"
 SetCompress off
 SetOutPath "$INSTDIR\modelos"
 File /r "runtime\modelos\*"
 SetOutPath "$INSTDIR\voz"
 File /r "runtime\voz\*"
 SetCompress auto
 SetOutPath "$INSTDIR"
 WriteUninstaller "$INSTDIR\Desinstalar.exe"
 CreateDirectory "$SMPROGRAMS\AURA"
 CreateShortcut "$SMPROGRAMS\AURA\AURA.lnk" "$INSTDIR\AURA-Nativa.exe"
 CreateShortcut "$SMPROGRAMS\AURA\Desinstalar.lnk" "$INSTDIR\Desinstalar.exe"
 CreateShortcut "$DESKTOP\AURA.lnk" "$INSTDIR\AURA-Nativa.exe"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA" "DisplayName" "AURA Inteligencia Artificial 3.1.0"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA" "InstallLocation" "$INSTDIR"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA" "DisplayVersion" "3.1.0"
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA" "NoModify" 1
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA" "NoRepair" 1
SectionEnd
Section "Uninstall"
 MessageBox MB_OKCANCEL|MB_ICONINFORMATION "Cierra AURA Inteligencia Artificial antes de continuar. Tus conversaciones y proyectos se conservarán." IDOK continue
 Abort
 continue:
 Delete "$DESKTOP\AURA.lnk"
 Delete "$SMPROGRAMS\AURA\AURA.lnk"
 Delete "$SMPROGRAMS\AURA\Desinstalar.lnk"
 RMDir "$SMPROGRAMS\AURA"
 Delete "$INSTDIR\AURA-Nativa.exe"
 Delete "$INSTDIR\Desinstalar.exe"
 Delete "$INSTDIR\LEEME.txt"
 RMDir /r "$INSTDIR\_internal"
 RMDir /r "$INSTDIR\motor"
 RMDir /r "$INSTDIR\modelos"
 RMDir /r "$INSTDIR\herramientas"
 RMDir /r "$INSTDIR\skills"
 RMDir /r "$INSTDIR\licencias"
 RMDir /r "$INSTDIR\voz"
 RMDir /r "$INSTDIR\fuente"
 RMDir "$INSTDIR"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AURA"
SectionEnd
