import struct

import wasm
import wasm.decode
import wasm.wasmtypes

import idc
import idaapi


SECTION_NAMES = {
    wasm.wasmtypes.SEC_TYPE: 'types',
    wasm.wasmtypes.SEC_IMPORT: 'imports',
    wasm.wasmtypes.SEC_FUNCTION: 'functions',
    wasm.wasmtypes.SEC_TABLE: 'tables',
    wasm.wasmtypes.SEC_MEMORY: 'memory',
    wasm.wasmtypes.SEC_GLOBAL: 'globals',
    wasm.wasmtypes.SEC_EXPORT: 'exports',
    wasm.wasmtypes.SEC_START: 'starts',
    wasm.wasmtypes.SEC_ELEMENT: 'elements',
    wasm.wasmtypes.SEC_CODE: 'code',
    wasm.wasmtypes.SEC_DATA: 'data',
}


def accept_file(f, n):
    f.seek(0)
    if f.read(4) != b'\x00asm':
        return 0

    if struct.unpack('<I', f.read(4))[0] != 0x1:
        return 0

    return 'WebAssembly v%d executable' % (0x1)


def offset_of(struc, fieldname):
    p = 0
    dec_meta = struc.get_decoder_meta()
    for field in struc.get_meta().fields:
        if field.name != fieldname:
            p += dec_meta['lengths'][field.name]
        else:
            return p
    raise KeyError('field not found: ' + fieldname)


def size_of(struc, fieldname=None):
    if fieldname is not None:
        # size of the given field, by name
        dec_meta = struc.get_decoder_meta()
        return dec_meta['lengths'][fieldname]
    else:
        # size of the entire given struct
        return sum(struc.get_decoder_meta()['lengths'].values())


import collections
Field = collections.namedtuple('Field', ['offset', 'name', 'size'])

def get_fields(struc):
    p = 0
    dec_meta = struc.get_decoder_meta()
    for field in struc.get_meta().fields:
        flen = dec_meta['lengths'][field.name]
        if flen > 0:
            yield Field(p, field.name, flen)
        p += flen


def MakeN(addr, size):
    if size == 1:
        idc.MakeByte(addr)
    elif size == 2:
        idc.MakeWord(addr)
    elif size == 4:
        idc.MakeDword(addr)
    elif size == 8:
        idc.MakeQword(addr)


def load_code_section(section, p):
    idc.MakeName(p + offset_of(section.data, 'id'), 'code_id')
    MakeN(p + offset_of(section.data, 'id'), size_of(section.data, 'id'))

    ppayload = p + offset_of(section.data, 'payload')
    idc.MakeName(ppayload + offset_of(section.data.payload, 'count'), 'function_count')
    MakeN(ppayload + offset_of(section.data.payload, 'count'), size_of(section.data.payload, 'count'))

    pbodies = ppayload + offset_of(section.data.payload, 'bodies')
    pcur = pbodies
    for i, body in enumerate(section.data.payload.bodies):
        fname = 'function_%X' % (i)
        idc.MakeName(pcur, fname)

        idc.MakeName(pcur + offset_of(body, 'local_count'), fname + '_local_count')
        MakeN(pcur + offset_of(body, 'local_count'), size_of(body, 'local_count'))

        if size_of(body, 'locals') > 0:
            idc.MakeName(pcur + offset_of(body, 'locals'), fname + '_locals')
            for j in range(size_of(body, 'locals')):
                idc.MakeByte(pcur + offset_of(body, 'locals') + j)

        idc.MakeName(pcur + offset_of(body, 'code'), fname + '_code')
        idc.MakeCode(pcur + offset_of(body, 'code'))

        pcur += size_of(body)


SECTION_LOADERS = {
    wasm.wasmtypes.SEC_CODE: load_code_section,
}


def load_file(f, neflags, format):
    f.seek(0x0, os.SEEK_END)
    flen = f.tell()
    f.seek(0x0)
    buf = f.read(flen)

    idaapi.set_processor_type('wasm', idaapi.SETPROC_ALL)

    f.seek(0x0)
    f.file2base(0, 0, len(buf), True)

    p = 0
    sections = wasm.decode.decode_module(buf)
    for i, section in enumerate(sections):
        if i == 0:
            sname = 'header'
        else:
            if section.data.id == 0:
                # fetch custom name
                sname = ''
            else:
                sname = SECTION_NAMES.get(section.data.id, 'unknown')

        if sname != 'header' and section.data.id == wasm.wasmtypes.SEC_CODE:
            stype = 'CODE'
        else:
            stype = 'DATA'

        slen = sum(section.data.get_decoder_meta()['lengths'].values())
        idaapi.add_segm(0, p, p + slen, sname, stype)

        if sname != 'header':
            loader = SECTION_LOADERS.get(section.data.id)
            if loader is not None:
                loader(section, p)

        p += slen

    # magic
    idc.MakeDword(0x0)
    idc.MakeName(0x0, 'WASM_MAGIC')
    # version
    idc.MakeDword(0x4)
    idc.MakeName(0x4, 'WASM_VERSION')

    return 1
