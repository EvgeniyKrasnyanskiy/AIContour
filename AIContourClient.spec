# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['client_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pydicom', 'pydicom._dicom_dict', 'pydicom._private_dict', 'pydicom._uid_dict', 'pydicom._version', 'pydicom.charset', 'pydicom.cli', 'pydicom.cli.codify', 'pydicom.cli.main', 'pydicom.cli.show', 'pydicom.config', 'pydicom.data', 'pydicom.data.data_manager', 'pydicom.data.download', 'pydicom.data.retry', 'pydicom.datadict', 'pydicom.dataelem', 'pydicom.dataset', 'pydicom.dicomio', 'pydicom.encaps', 'pydicom.encoders', 'pydicom.env_info', 'pydicom.errors', 'pydicom.examples', 'pydicom.filebase', 'pydicom.filereader', 'pydicom.fileset', 'pydicom.fileutil', 'pydicom.filewriter', 'pydicom.hooks', 'pydicom.jsonrep', 'pydicom.misc', 'pydicom.multival', 'pydicom.overlays', 'pydicom.overlays.numpy_handler', 'pydicom.pixel_data_handlers', 'pydicom.pixel_data_handlers.gdcm_handler', 'pydicom.pixel_data_handlers.jpeg_ls_handler', 'pydicom.pixel_data_handlers.numpy_handler', 'pydicom.pixel_data_handlers.pillow_handler', 'pydicom.pixel_data_handlers.pylibjpeg_handler', 'pydicom.pixel_data_handlers.rle_handler', 'pydicom.pixel_data_handlers.util', 'pydicom.pixels', 'pydicom.pixels.common', 'pydicom.pixels.decoders', 'pydicom.pixels.decoders.base', 'pydicom.pixels.decoders.gdcm', 'pydicom.pixels.decoders.pillow', 'pydicom.pixels.decoders.pyjpegls', 'pydicom.pixels.decoders.pylibjpeg', 'pydicom.pixels.decoders.rle', 'pydicom.pixels.encoders', 'pydicom.pixels.encoders.base', 'pydicom.pixels.encoders.gdcm', 'pydicom.pixels.encoders.native', 'pydicom.pixels.encoders.pyjpegls', 'pydicom.pixels.encoders.pylibjpeg', 'pydicom.pixels.processing', 'pydicom.pixels.utils', 'pydicom.sequence', 'pydicom.sr', 'pydicom.sr._cid_dict', 'pydicom.sr._concepts_dict', 'pydicom.sr._snomed_dict', 'pydicom.sr.codedict', 'pydicom.sr.coding', 'pydicom.tag', 'pydicom.uid', 'pydicom.util', 'pydicom.util.codify', 'pydicom.util.dump', 'pydicom.util.fixer', 'pydicom.util.hexutil', 'pydicom.util.leanread', 'pydicom.valuerep', 'pydicom.values', 'pydicom.waveforms', 'pydicom.waveforms.numpy_handler', 'pynetdicom', 'pynetdicom.__main__', 'pynetdicom._config', 'pynetdicom._globals', 'pynetdicom._handlers', 'pynetdicom._validators', 'pynetdicom._version', 'pynetdicom.acse', 'pynetdicom.ae', 'pynetdicom.apps', 'pynetdicom.apps.common', 'pynetdicom.apps.echoscp', 'pynetdicom.apps.echoscp.echoscp', 'pynetdicom.apps.echoscu', 'pynetdicom.apps.echoscu.echoscu', 'pynetdicom.apps.findscu', 'pynetdicom.apps.findscu.findscu', 'pynetdicom.apps.getscu', 'pynetdicom.apps.getscu.getscu', 'pynetdicom.apps.movescu', 'pynetdicom.apps.movescu.movescu', 'pynetdicom.apps.qrscp', 'pynetdicom.apps.qrscp.db', 'pynetdicom.apps.qrscp.handlers', 'pynetdicom.apps.qrscp.qrscp', 'pynetdicom.apps.storescp', 'pynetdicom.apps.storescp.storescp', 'pynetdicom.apps.storescu', 'pynetdicom.apps.storescu.storescu', 'pynetdicom.apps.tests', 'pynetdicom.apps.tests.test_common', 'pynetdicom.apps.tests.test_echoscp', 'pynetdicom.apps.tests.test_echoscu', 'pynetdicom.apps.tests.test_findscu', 'pynetdicom.apps.tests.test_getscu', 'pynetdicom.apps.tests.test_movescu', 'pynetdicom.apps.tests.test_qrscp_db', 'pynetdicom.apps.tests.test_qrscp_echo', 'pynetdicom.apps.tests.test_qrscp_find', 'pynetdicom.apps.tests.test_qrscp_get', 'pynetdicom.apps.tests.test_qrscp_move', 'pynetdicom.apps.tests.test_qrscp_store', 'pynetdicom.apps.tests.test_storescp', 'pynetdicom.apps.tests.test_storescu', 'pynetdicom.association', 'pynetdicom.benchmarks', 'pynetdicom.benchmarks.bench_c_send', 'pynetdicom.benchmarks.bench_dimse_message', 'pynetdicom.benchmarks.bench_pdu', 'pynetdicom.benchmarks.bench_presentation', 'pynetdicom.dimse', 'pynetdicom.dimse_messages', 'pynetdicom.dimse_primitives', 'pynetdicom.dsutils', 'pynetdicom.dul', 'pynetdicom.events', 'pynetdicom.fsm', 'pynetdicom.pdu', 'pynetdicom.pdu_items', 'pynetdicom.pdu_primitives', 'pynetdicom.presentation', 'pynetdicom.service_class', 'pynetdicom.service_class_n', 'pynetdicom.sop_class', 'pynetdicom.status', 'pynetdicom.tests', 'pynetdicom.tests.benchmark_script', 'pynetdicom.tests.encoded_dimse_msg', 'pynetdicom.tests.encoded_dimse_n_msg', 'pynetdicom.tests.encoded_pdu_items', 'pynetdicom.tests.hide_modules', 'pynetdicom.tests.parrot', 'pynetdicom.tests.test_acse', 'pynetdicom.tests.test_ae', 'pynetdicom.tests.test_assoc', 'pynetdicom.tests.test_assoc_n', 'pynetdicom.tests.test_assoc_user', 'pynetdicom.tests.test_cli', 'pynetdicom.tests.test_dimse_c', 'pynetdicom.tests.test_dimse_msg', 'pynetdicom.tests.test_dimse_n', 'pynetdicom.tests.test_dimse_provider', 'pynetdicom.tests.test_dsutils', 'pynetdicom.tests.test_dul', 'pynetdicom.tests.test_environment', 'pynetdicom.tests.test_events', 'pynetdicom.tests.test_fsm', 'pynetdicom.tests.test_logging', 'pynetdicom.tests.test_pdu', 'pynetdicom.tests.test_pdu_items', 'pynetdicom.tests.test_presentation', 'pynetdicom.tests.test_primitives', 'pynetdicom.tests.test_service_class', 'pynetdicom.tests.test_service_n', 'pynetdicom.tests.test_service_non_patient', 'pynetdicom.tests.test_service_qr', 'pynetdicom.tests.test_service_relevant_patient', 'pynetdicom.tests.test_service_storage', 'pynetdicom.tests.test_service_substance_admin', 'pynetdicom.tests.test_service_verification', 'pynetdicom.tests.test_sop', 'pynetdicom.tests.test_status', 'pynetdicom.tests.test_timer', 'pynetdicom.tests.test_transport', 'pynetdicom.tests.test_utils', 'pynetdicom.tests.test_validators', 'pynetdicom.tests.utils', 'pynetdicom.timer', 'pynetdicom.transport', 'pynetdicom.utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'totalsegmentator', 'SimpleITK', 'nibabel', 'matplotlib', 'pandas', 'h5py', 'scipy', 'contour_engine'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AIContourClient',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.ico'],
)
