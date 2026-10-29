; SPDX-License-Identifier: GPL-3.0-or-later
; Copyright (C) 2026 Daniel Ricardo Novoa

#ifndef MiAppVersion
  #define MiAppVersion "0.1.0"
#endif

#define MiAppName "DiagUSB"
#define MiAppPublisher "Daniel Ricardo Novoa"
#define MiAppURL "https://github.com/AurigaNet/DiagUSB"
#define MiAppExe "DiagUSB.exe"
#define MiPayload "..\dist\DiagUSB"

[Setup]
AppId={{B6A7F3C2-9F1E-4C5D-8A3B-7E2D4C6F1A90}
AppName={#MiAppName}
AppVersion={#MiAppVersion}
AppVerName={#MiAppName} {#MiAppVersion}
AppPublisher={#MiAppPublisher}
AppPublisherURL={#MiAppURL}
AppSupportURL={#MiAppURL}
AppUpdatesURL={#MiAppURL}
AppCopyright=Copyright (C) 2026 Daniel Ricardo Novoa
VersionInfoVersion=0.1.0.0
VersionInfoProductName={#MiAppName}
VersionInfoDescription=Instalador de DiagUSB
VersionInfoCompany={#MiAppPublisher}
VersionInfoCopyright=Copyright (C) 2026 Daniel Ricardo Novoa
DefaultDirName={localappdata}\Programs\DiagUSB
DefaultGroupName=DiagUSB
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
DisableWelcomePage=no
DisableStartupPrompt=yes
UsePreviousAppDir=no
UsePreviousGroup=no
PrivilegesRequired=lowest
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=DiagUSB-Setup-{#MiAppVersion}
SetupIconFile=..\assets\branding\diagusb.ico
WizardStyle=modern dark
WizardImageFile=..\assets\branding\wizard.bmp
WizardSmallImageFile=..\assets\branding\wizard-small.bmp
WizardImageBackColor=$0024140A
WizardSmallImageBackColor=$0024140A
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MiAppExe}
UninstallDisplayName={#MiAppName} {#MiAppVersion}
CreateUninstallRegKey=yes
Uninstallable=yes
AllowNoIcons=yes
SetupMutex=DiagUSB_Setup_Mutex

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#MiPayload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\LEGAL.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\SECURITY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\DiagUSB"; Filename: "{app}\{#MiAppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MiAppExe}"; Check: EsPC
Name: "{group}\Desinstalar DiagUSB"; Filename: "{uninstallexe}"; Check: EsPC
Name: "{autodesktop}\DiagUSB"; Filename: "{app}\{#MiAppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MiAppExe}"; Check: EsPC

[Run]
Filename: "{app}\{#MiAppExe}"; Description: "Abrir DiagUSB"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\instalado.flag"
Type: dirifempty; Name: "{app}"

[Code]
const
  DRIVE_REMOVABLE = 2;
  ESPACIO_MINIMO = 80 * 1024 * 1024;

var
  PaginaModo: TWizardPage;
  RadioPC: TNewRadioButton;
  RadioUSB: TNewRadioButton;
  TextoPC: TNewStaticText;
  TextoUSB: TNewStaticText;
  EtiquetaUnidad: TNewStaticText;
  ComboUnidad: TNewComboBox;
  BotonActualizar: TNewButton;
  EtiquetaAviso: TNewStaticText;
  EtiquetaAyuda: TNewStaticText;
  Unidades: TStringList;
  UnidadUSB: String;
  ModoPC: Boolean;

function GetDriveType(lpRootPathName: String): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function GetDiskFreeSpaceEx(lpDirectoryName: String;
  var lpFreeBytesAvailableToCaller, lpTotalNumberOfBytes,
  lpTotalNumberOfFreeBytes: Int64): Boolean;
  external 'GetDiskFreeSpaceExW@kernel32.dll stdcall';

function EsPC: Boolean;
begin
  Result := ModoPC;
end;

procedure ActualizarModo;
begin
  ModoPC := RadioPC.Checked;
  ComboUnidad.Enabled := (not ModoPC) and (Unidades.Count > 0);
  BotonActualizar.Enabled := not ModoPC;

  if ModoPC then
  begin
    EtiquetaAyuda.Caption := 'Se instalará en tu perfil de usuario, sin pedir permisos de administrador. Los datos se guardan separados en %LOCALAPPDATA%\DiagUSB.';
    EtiquetaAviso.Caption := '';
    EtiquetaAviso.Visible := False;
  end
  else
  begin
    EtiquetaAyuda.Caption := 'Se copiará todo en X:\DiagUSB. Los datos y los informes viajan con el pendrive; no se crea desinstalador.';
    if Unidades.Count = 0 then
    begin
      EtiquetaAviso.Caption := 'No se detectaron pendrives extraíbles. Conectá uno y pulsá Actualizar.';
      EtiquetaAviso.Visible := True;
    end
    else
    begin
      EtiquetaAviso.Caption := '';
      EtiquetaAviso.Visible := False;
    end;
  end;
end;

procedure CargarUnidades;
var
  i: Integer;
  raiz: String;
  libre, total, libreTotal: Int64;
begin
  Unidades.Clear;
  ComboUnidad.Items.Clear;

  for i := Ord('C') to Ord('Z') do
  begin
    raiz := Chr(i) + ':\';
    if GetDriveType(raiz) = DRIVE_REMOVABLE then
    begin
      if GetDiskFreeSpaceEx(raiz, libre, total, libreTotal) then
      begin
        if libre >= ESPACIO_MINIMO then
        begin
          Unidades.Add(raiz);
          ComboUnidad.Items.Add(raiz + '  (' + IntToStr(libre div 1048576) + ' MB libres)');
        end;
      end;
    end;
  end;

  if ComboUnidad.Items.Count > 0 then
    ComboUnidad.ItemIndex := 0;

  ActualizarModo;
end;

procedure CambioModo(Sender: TObject);
begin
  ActualizarModo;
end;

procedure ActivarPaginaModo(Sender: TWizardPage);
begin
  CargarUnidades;
end;

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel1.Caption := 'Bienvenido a DiagUSB';
  WizardForm.WelcomeLabel2.Caption :=
    'Diagnóstico técnico portable para Windows 10 y 11.' + #13#10 + #13#10 +
    'Este asistente instala DiagUSB en este equipo o en un pendrive extraíble. ' +
    'En el equipo, los datos quedan separados y se conservan al desinstalar. ' +
    'En el pendrive, DiagUSB funciona de forma portable, sin registro de Windows.';
  WizardForm.WelcomeLabel2.WordWrap := True;

  Unidades := TStringList.Create;
  ModoPC := True;

  PaginaModo := CreateCustomPage(wpWelcome,
    '¿Dónde querés instalar DiagUSB?',
    'Elegí el destino. Después se copiarán los archivos y verás el progreso.');

  RadioPC := TNewRadioButton.Create(PaginaModo);
  RadioPC.Parent := PaginaModo.Surface;
  RadioPC.Left := 0;
  RadioPC.Top := 0;
  RadioPC.Width := PaginaModo.SurfaceWidth;
  RadioPC.Height := ScaleY(24);
  RadioPC.Caption := 'En este equipo (recomendado)';
  RadioPC.Font.Size := 11;
  RadioPC.Font.Style := [fsBold];
  RadioPC.Checked := True;
  RadioPC.OnClick := @CambioModo;

  TextoPC := TNewStaticText.Create(PaginaModo);
  TextoPC.Parent := PaginaModo.Surface;
  TextoPC.Left := ScaleX(22);
  TextoPC.Top := ScaleY(27);
  TextoPC.Width := PaginaModo.SurfaceWidth - ScaleX(22);
  TextoPC.AutoSize := False;
  TextoPC.WordWrap := True;
  TextoPC.Caption := 'Instalación por usuario, sin UAC. Accesos en Inicio y escritorio, desinstalador y datos en %LOCALAPPDATA%\DiagUSB.';
  TextoPC.Font.Size := 9;
  TextoPC.Height := TextoPC.AdjustHeight;

  RadioUSB := TNewRadioButton.Create(PaginaModo);
  RadioUSB.Parent := PaginaModo.Surface;
  RadioUSB.Left := 0;
  RadioUSB.Top := ScaleY(78);
  RadioUSB.Width := PaginaModo.SurfaceWidth;
  RadioUSB.Height := ScaleY(24);
  RadioUSB.Caption := 'En un pendrive portable';
  RadioUSB.Font.Size := 11;
  RadioUSB.Font.Style := [fsBold];
  RadioUSB.OnClick := @CambioModo;

  TextoUSB := TNewStaticText.Create(PaginaModo);
  TextoUSB.Parent := PaginaModo.Surface;
  TextoUSB.Left := ScaleX(22);
  TextoUSB.Top := ScaleY(105);
  TextoUSB.Width := PaginaModo.SurfaceWidth - ScaleX(22);
  TextoUSB.AutoSize := False;
  TextoUSB.WordWrap := True;
  TextoUSB.Caption := 'Copia portable en X:\DiagUSB. No toca el registro de Windows y no instala desinstalador.';
  TextoUSB.Font.Size := 9;
  TextoUSB.Height := TextoUSB.AdjustHeight;

  EtiquetaUnidad := TNewStaticText.Create(PaginaModo);
  EtiquetaUnidad.Parent := PaginaModo.Surface;
  EtiquetaUnidad.Left := 0;
  EtiquetaUnidad.Top := ScaleY(148);
  EtiquetaUnidad.Caption := 'Pendrive:';
  EtiquetaUnidad.Font.Style := [fsBold];

  ComboUnidad := TNewComboBox.Create(PaginaModo);
  ComboUnidad.Parent := PaginaModo.Surface;
  ComboUnidad.Left := ScaleX(70);
  ComboUnidad.Top := ScaleY(145);
  ComboUnidad.Width := PaginaModo.SurfaceWidth - ScaleX(150);
  ComboUnidad.Style := csDropDownList;
  ComboUnidad.Enabled := False;

  BotonActualizar := TNewButton.Create(PaginaModo);
  BotonActualizar.Parent := PaginaModo.Surface;
  BotonActualizar.Caption := 'Actualizar';
  BotonActualizar.Left := PaginaModo.SurfaceWidth - ScaleX(72);
  BotonActualizar.Top := ScaleY(143);
  BotonActualizar.Width := ScaleX(72);
  BotonActualizar.Height := ScaleY(25);
  BotonActualizar.OnClick := @CambioModo;
  BotonActualizar.Enabled := False;

  EtiquetaAviso := TNewStaticText.Create(PaginaModo);
  EtiquetaAviso.Parent := PaginaModo.Surface;
  EtiquetaAviso.Left := 0;
  EtiquetaAviso.Top := ScaleY(180);
  EtiquetaAviso.Width := PaginaModo.SurfaceWidth;
  EtiquetaAviso.AutoSize := False;
  EtiquetaAviso.WordWrap := True;
  EtiquetaAviso.Height := ScaleY(34);
  EtiquetaAviso.Visible := False;
  EtiquetaAviso.Font.Style := [fsBold];

  EtiquetaAyuda := TNewStaticText.Create(PaginaModo);
  EtiquetaAyuda.Parent := PaginaModo.Surface;
  EtiquetaAyuda.Left := 0;
  EtiquetaAyuda.Top := ScaleY(224);
  EtiquetaAyuda.Width := PaginaModo.SurfaceWidth;
  EtiquetaAyuda.AutoSize := False;
  EtiquetaAyuda.WordWrap := True;
  EtiquetaAyuda.Height := ScaleY(52);
  EtiquetaAyuda.Font.Size := 9;

  PaginaModo.OnActivate := @ActivarPaginaModo;
  ActualizarModo;

  WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Programs\DiagUSB');
end;

procedure DeinitializeSetup;
begin
  Unidades.Free;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> PaginaModo.ID then
    Exit;

  if RadioUSB.Checked then
  begin
    if ComboUnidad.ItemIndex < 0 then
    begin
      MsgBox('Conectá un pendrive extraíble y pulsá Actualizar antes de continuar.',
        mbError, MB_OK);
      Result := False;
      Exit;
    end;
    UnidadUSB := Unidades[ComboUnidad.ItemIndex];
    if not DirExists(UnidadUSB) then
    begin
      MsgBox('El pendrive seleccionado ya no está disponible. Actualizá la lista e intentá de nuevo.',
        mbError, MB_OK);
      Result := False;
      Exit;
    end;
    ModoPC := False;
    WizardForm.DirEdit.Text := UnidadUSB + 'DiagUSB';
  end
  else
  begin
    ModoPC := True;
    UnidadUSB := '';
    WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Programs\DiagUSB');
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    if ModoPC then
    begin
      WizardForm.FinishedHeadingLabel.Caption := 'DiagUSB está listo';
      WizardForm.FinishedLabel.Caption :=
        'DiagUSB se instaló en este equipo.' + #13#10 + #13#10 +
        'Los datos se guardan en ' + ExpandConstant('{localappdata}\DiagUSB') +
        ' y se conservan si desinstalás el programa.';
    end
    else
    begin
      WizardForm.FinishedHeadingLabel.Caption := 'DiagUSB está listo en el pendrive';
      WizardForm.FinishedLabel.Caption :=
        'DiagUSB se copió en ' + WizardForm.DirEdit.Text + '.' + #13#10 + #13#10 +
        'Para usarlo en otro equipo, abrí DiagUSB desde esa carpeta. ' +
        'Los datos y los informes quedan guardados en el pendrive.';
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  datos: String;
begin
  if CurStep <> ssDone then
    Exit;

  if ModoPC then
  begin
    datos := ExpandConstant('{localappdata}\DiagUSB');
    ForceDirectories(datos);
    SaveStringToFile(ExpandConstant('{app}\instalado.flag'),
      '# DiagUSB: datos de usuario' + #13#10 + datos + #13#10, False);
  end
  else
  begin
    DeleteFile(ExpandConstant('{app}\instalado.flag'));
    DeleteFile(ExpandConstant('{app}\unins000.exe'));
    DeleteFile(ExpandConstant('{app}\unins000.dat'));
    DeleteFile(ExpandConstant('{app}\unins000.msg'));
    RegDeleteKeyIncludingSubkeys(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B6A7F3C2-9F1E-4C5D-8A3B-7E2D4C6F1A90}_is1');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  datos: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  if UninstallSilent then
    Exit;

  datos := ExpandConstant('{localappdata}\DiagUSB');
  if DirExists(datos) then
  begin
    if MsgBox('¿Querés eliminar también los datos de DiagUSB?' + #13#10 + #13#10 +
        datos + #13#10 + #13#10 +
        'Incluye el registro de análisis, los snapshots, los informes y la base de conocimiento local. ' +
        'Si elegís No, los datos se conservan para una próxima instalación.',
        mbConfirmation, MB_YESNO) = IDYES then
      DelTree(datos, True, True, True);
  end;
end;
