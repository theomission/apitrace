##########################################################################
#
# Copyright 2008-2010 VMware, Inc.
# All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
##########################################################################/


"""GL tracing generator."""


import specs.stdapi as stdapi
import specs.glapi as glapi
import specs.glparams as glparams
from specs.glxapi import glxapi
from trace import Tracer, dump_instance


class TypeGetter(stdapi.Visitor):
    '''Determine which glGet*v function that matches the specified type.'''

    def __init__(self, prefix = 'glGet', long_suffix = True, ext_suffix = ''):
        self.prefix = prefix
        self.long_suffix = long_suffix
        self.ext_suffix = ext_suffix

    def visit_const(self, const):
        return self.visit(const.type)

    def visit_alias(self, alias):
        if alias.expr == 'GLboolean':
            if self.long_suffix:
                suffix = 'Booleanv'
                arg_type = alias.expr
            else:
                suffix = 'iv'
                arg_type = 'GLint'
        elif alias.expr == 'GLdouble':
            if self.long_suffix:
                suffix = 'Doublev'
                arg_type = alias.expr
            else:
                suffix = 'dv'
                arg_type = alias.expr
        elif alias.expr == 'GLfloat':
            if self.long_suffix:
                suffix = 'Floatv'
                arg_type = alias.expr
            else:
                suffix = 'fv'
                arg_type = alias.expr
        elif alias.expr in ('GLint', 'GLuint', 'GLsizei'):
            if self.long_suffix:
                suffix = 'Integerv'
                arg_type = 'GLint'
            else:
                suffix = 'iv'
                arg_type = 'GLint'
        else:
            print alias.expr
            assert False
        function_name = self.prefix + suffix + self.ext_suffix
        return function_name, arg_type
    
    def visit_enum(self, enum):
        return self.visit(glapi.GLint)

    def visit_bitmask(self, bitmask):
        return self.visit(glapi.GLint)

    def visit_opaque(self, pointer):
        return self.prefix + 'Pointerv' + self.ext_suffix, 'GLvoid *'


class GlTracer(Tracer):

    arrays = [
        ("Vertex", "VERTEX"),
        ("Normal", "NORMAL"),
        ("Color", "COLOR"),
        ("Index", "INDEX"),
        ("TexCoord", "TEXTURE_COORD"),
        ("EdgeFlag", "EDGE_FLAG"),
        ("FogCoord", "FOG_COORD"),
        ("SecondaryColor", "SECONDARY_COLOR"),
    ]
    arrays.reverse()

    def header(self, api):
        Tracer.header(self, api)

        print '#include "gltrace.hpp"'
        print
        print '// Whether user arrays were used'
        print 'static bool __user_arrays = false;'
        print 'static bool __user_arrays_arb = false;'
        print 'static bool __user_arrays_nv = false;'
        print
        
        # Which glVertexAttrib* variant to use
        print 'enum vertex_attrib {'
        print '    VERTEX_ATTRIB,'
        print '    VERTEX_ATTRIB_ARB,'
        print '    VERTEX_ATTRIB_NV,'
        print '};'
        print
        print 'static vertex_attrib __get_vertex_attrib(void) {'
        print '    if (__user_arrays_arb || __user_arrays_nv) {'
        print '        GLboolean __vertex_program = GL_FALSE;'
        print '        __glGetBooleanv(GL_VERTEX_PROGRAM_ARB, &__vertex_program);'
        print '        if (__vertex_program) {'
        print '            if (__user_arrays_nv) {'
        print '                GLint __vertex_program_binding_nv = 0;'
        print '                __glGetIntegerv(GL_VERTEX_PROGRAM_BINDING_NV, &__vertex_program_binding_nv);'
        print '                if (__vertex_program_binding_nv) {'
        print '                    return VERTEX_ATTRIB_NV;'
        print '                }'
        print '            }'
        print '            return VERTEX_ATTRIB_ARB;'
        print '        }'
        print '    }'
        print '    return VERTEX_ATTRIB;'
        print '}'
        print

        # Whether we need user arrays
        print 'static inline bool __need_user_arrays(void)'
        print '{'
        print '    if (!__user_arrays) {'
        print '        return false;'
        print '    }'
        print

        for camelcase_name, uppercase_name in self.arrays:
            function_name = 'gl%sPointer' % camelcase_name
            enable_name = 'GL_%s_ARRAY' % uppercase_name
            binding_name = 'GL_%s_ARRAY_BUFFER_BINDING' % uppercase_name
            print '    // %s' % function_name
            self.array_prolog(api, uppercase_name)
            print '    if (__glIsEnabled(%s)) {' % enable_name
            print '        GLint __binding = 0;'
            print '        __glGetIntegerv(%s, &__binding);' % binding_name
            print '        if (!__binding) {'
            self.array_cleanup(api, uppercase_name)
            print '            return true;'
            print '        }'
            print '    }'
            self.array_epilog(api, uppercase_name)
            print

        print '    vertex_attrib __vertex_attrib = __get_vertex_attrib();'
        print
        print '    // glVertexAttribPointer'
        print '    if (__vertex_attrib == VERTEX_ATTRIB) {'
        print '        GLint __max_vertex_attribs = 0;'
        print '        __glGetIntegerv(GL_MAX_VERTEX_ATTRIBS, &__max_vertex_attribs);'
        print '        for (GLint index = 0; index < __max_vertex_attribs; ++index) {'
        print '            GLint __enabled = 0;'
        print '            __glGetVertexAttribiv(index, GL_VERTEX_ATTRIB_ARRAY_ENABLED, &__enabled);'
        print '            if (__enabled) {'
        print '                GLint __binding = 0;'
        print '                __glGetVertexAttribiv(index, GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING, &__binding);'
        print '                if (!__binding) {'
        print '                    return true;'
        print '                }'
        print '            }'
        print '        }'
        print '    }'
        print
        print '    // glVertexAttribPointerARB'
        print '    if (__vertex_attrib == VERTEX_ATTRIB_ARB) {'
        print '        GLint __max_vertex_attribs = 0;'
        print '        __glGetIntegerv(GL_MAX_VERTEX_ATTRIBS_ARB, &__max_vertex_attribs);'
        print '        for (GLint index = 0; index < __max_vertex_attribs; ++index) {'
        print '            GLint __enabled = 0;'
        print '            __glGetVertexAttribivARB(index, GL_VERTEX_ATTRIB_ARRAY_ENABLED_ARB, &__enabled);'
        print '            if (__enabled) {'
        print '                GLint __binding = 0;'
        print '                __glGetVertexAttribivARB(index, GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING_ARB, &__binding);'
        print '                if (!__binding) {'
        print '                    return true;'
        print '                }'
        print '            }'
        print '        }'
        print '    }'
        print
        print '    // glVertexAttribPointerNV'
        print '    if (__vertex_attrib == VERTEX_ATTRIB_NV) {'
        print '        for (GLint index = 0; index < 16; ++index) {'
        print '            GLint __enabled = 0;'
        print '            __glGetIntegerv(GL_VERTEX_ATTRIB_ARRAY0_NV + index, &__enabled);'
        print '            if (__enabled) {'
        print '                return true;'
        print '            }'
        print '        }'
        print '    }'
        print

        print '    return false;'
        print '}'
        print

        print 'static void __trace_user_arrays(GLuint maxindex);'
        print

        print 'struct buffer_mapping {'
        print '    void *map;'
        print '    GLint length;'
        print '    bool write;'
        print '    bool explicit_flush;'
        print '};'
        print
        for target in self.buffer_targets:
            print 'struct buffer_mapping __%s_mapping;' % target.lower();
        print
        print 'static inline struct buffer_mapping *'
        print 'get_buffer_mapping(GLenum target) {'
        print '    switch(target) {'
        for target in self.buffer_targets:
            print '    case GL_%s:' % target
            print '        return & __%s_mapping;' % target.lower()
        print '    default:'
        print '        OS::DebugMessage("apitrace: warning: unknown buffer target 0x%04X\\n", target);'
        print '        return NULL;'
        print '    }'
        print '}'
        print

        # Generate a helper function to determine whether a parameter name
        # refers to a symbolic value or not
        print 'static bool'
        print 'is_symbolic_pname(GLenum pname) {'
        print '    switch(pname) {'
        for function, type, count, name in glparams.parameters:
            if type is glapi.GLenum:
                print '    case %s:' % name
        print '        return true;'
        print '    default:'
        print '        return false;'
        print '    }'
        print '}'
        print
        
        # Generate a helper function to determine whether a parameter value is
        # potentially symbolic or not; i.e., if the value can be represented in
        # an enum or not
        print 'template<class T>'
        print 'static inline bool'
        print 'is_symbolic_param(T param) {'
        print '    return static_cast<T>(static_cast<GLenum>(param)) == param;'
        print '}'
        print

        # Generate a helper function to know how many elements a parameter has
        print 'static size_t'
        print '__gl_param_size(GLenum pname) {'
        print '    switch(pname) {'
        for function, type, count, name in glparams.parameters:
            if type is not None:
                print '    case %s: return %u;' % (name, count)
        print '    case GL_COMPRESSED_TEXTURE_FORMATS: {'
        print '            GLint num_compressed_texture_formats = 0;'
        print '            __glGetIntegerv(GL_NUM_COMPRESSED_TEXTURE_FORMATS, &num_compressed_texture_formats);'
        print '            return num_compressed_texture_formats;'
        print '        }'
        print '    default:'
        print r'        OS::DebugMessage("apitrace: warning: %s: unknown GLenum 0x%04X\n", __FUNCTION__, pname);'
        print '        return 1;'
        print '    }'
        print '}'
        print

    array_pointer_function_names = set((
        "glVertexPointer",
        "glNormalPointer",
        "glColorPointer",
        "glIndexPointer",
        "glTexCoordPointer",
        "glEdgeFlagPointer",
        "glFogCoordPointer",
        "glSecondaryColorPointer",
        
        "glInterleavedArrays",

        "glVertexPointerEXT",
        "glNormalPointerEXT",
        "glColorPointerEXT",
        "glIndexPointerEXT",
        "glTexCoordPointerEXT",
        "glEdgeFlagPointerEXT",
        "glFogCoordPointerEXT",
        "glSecondaryColorPointerEXT",

        "glVertexAttribPointer",
        "glVertexAttribPointerARB",
        "glVertexAttribPointerNV",
        "glVertexAttribIPointer",
        "glVertexAttribIPointerEXT",
        "glVertexAttribLPointer",
        "glVertexAttribLPointerEXT",
        
        #"glMatrixIndexPointerARB",
    ))

    draw_function_names = set((
        'glDrawArrays',
        'glDrawElements',
        'glDrawRangeElements',
        'glMultiDrawArrays',
        'glMultiDrawElements',
        'glDrawArraysInstanced',
        "glDrawArraysInstancedBaseInstance",
        'glDrawElementsInstanced',
        'glDrawArraysInstancedARB',
        'glDrawElementsInstancedARB',
        'glDrawElementsBaseVertex',
        'glDrawRangeElementsBaseVertex',
        'glDrawElementsInstancedBaseVertex',
        "glDrawElementsInstancedBaseInstance",
        "glDrawElementsInstancedBaseVertexBaseInstance",
        'glMultiDrawElementsBaseVertex',
        'glDrawArraysIndirect',
        'glDrawElementsIndirect',
        'glDrawArraysEXT',
        'glDrawRangeElementsEXT',
        'glDrawRangeElementsEXT_size',
        'glMultiDrawArraysEXT',
        'glMultiDrawElementsEXT',
        'glMultiModeDrawArraysIBM',
        'glMultiModeDrawElementsIBM',
        'glDrawArraysInstancedEXT',
        'glDrawElementsInstancedEXT',
    ))

    interleaved_formats = [
         'GL_V2F',
         'GL_V3F',
         'GL_C4UB_V2F',
         'GL_C4UB_V3F',
         'GL_C3F_V3F',
         'GL_N3F_V3F',
         'GL_C4F_N3F_V3F',
         'GL_T2F_V3F',
         'GL_T4F_V4F',
         'GL_T2F_C4UB_V3F',
         'GL_T2F_C3F_V3F',
         'GL_T2F_N3F_V3F',
         'GL_T2F_C4F_N3F_V3F',
         'GL_T4F_C4F_N3F_V4F',
    ]

    def trace_function_impl_body(self, function):
        # Defer tracing of user array pointers...
        if function.name in self.array_pointer_function_names:
            print '    GLint __array_buffer = 0;'
            print '    __glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &__array_buffer);'
            print '    if (pointer) {'
            print '        if (!__array_buffer) {'
            print '            __user_arrays = true;'
            if function.name == "glVertexAttribPointerARB":
                print '            __user_arrays_arb = true;'
            if function.name == "glVertexAttribPointerNV":
                print '            __user_arrays_nv = true;'
            print '            Trace::localWriter.updateRegion(pointer);'
            print '        }'
            print '    }'

        # ... to the draw calls
        if function.name in self.draw_function_names:
            print '    if (__need_user_arrays()) {'
            arg_names = ', '.join([arg.name for arg in function.args[1:]])
            print '        GLuint maxindex = __%s_maxindex(%s);' % (function.name, arg_names)
            print '        __trace_user_arrays(maxindex);'
            print '    }'
        
        # Emit a fake memcpy on buffer uploads
        if function.name in ('glUnmapBuffer', 'glUnmapBufferARB', ):
            print '    struct buffer_mapping *mapping = get_buffer_mapping(target);'
            print '    if (mapping && mapping->write && !mapping->explicit_flush) {'
            self.emit_memcpy('mapping->map', 'mapping->map', 'mapping->length')
            print '    }'
        if function.name in ('glFlushMappedBufferRange', 'glFlushMappedBufferRangeAPPLE'):
            print '    struct buffer_mapping *mapping = get_buffer_mapping(target);'
            print '    if (mapping) {'
            if function.name.endswith('APPLE'):
                 print '        GLsizeiptr length = size;'
                 print '        mapping->explicit_flush = true;'
            print '        //assert(offset + length <= mapping->length);'
            self.emit_memcpy('(char *)mapping->map + offset', '(const char *)mapping->map + offset', 'length')
            print '    }'
        # FIXME: glFlushMappedNamedBufferRangeEXT

        # Don't leave vertex attrib locations to chance.  Instead emit fake
        # glBindAttribLocation calls to ensure that the same locations will be
        # used when retracing.  Trying to remap locations after the fact would
        # be an herculian task given that vertex attrib locations appear in
        # many entry-points, including non-shader related ones.
        if function.name == 'glLinkProgram':
            Tracer.dispatch_function(self, function)
            print '    GLint active_attributes = 0;'
            print '    __glGetProgramiv(program, GL_ACTIVE_ATTRIBUTES, &active_attributes);'
            print '    for (GLint attrib = 0; attrib < active_attributes; ++attrib) {'
            print '        GLint size = 0;'
            print '        GLenum type = 0;'
            print '        GLchar name[256];'
            # TODO: Use ACTIVE_ATTRIBUTE_MAX_LENGTH instead of 256
            print '        __glGetActiveAttrib(program, attrib, sizeof name, NULL, &size, &type, name);'
            print "        if (name[0] != 'g' || name[1] != 'l' || name[2] != '_') {"
            print '            GLint location = __glGetAttribLocation(program, name);'
            print '            if (location >= 0) {'
            bind_function = glapi.glapi.get_function_by_name('glBindAttribLocation')
            self.fake_call(bind_function, ['program', 'location', 'name'])
            print '            }'
            print '        }'
            print '    }'
        if function.name == 'glLinkProgramARB':
            Tracer.dispatch_function(self, function)
            print '    GLint active_attributes = 0;'
            print '    __glGetObjectParameterivARB(programObj, GL_OBJECT_ACTIVE_ATTRIBUTES_ARB, &active_attributes);'
            print '    for (GLint attrib = 0; attrib < active_attributes; ++attrib) {'
            print '        GLint size = 0;'
            print '        GLenum type = 0;'
            print '        GLcharARB name[256];'
            # TODO: Use ACTIVE_ATTRIBUTE_MAX_LENGTH instead of 256
            print '        __glGetActiveAttribARB(programObj, attrib, sizeof name, NULL, &size, &type, name);'
            print "        if (name[0] != 'g' || name[1] != 'l' || name[2] != '_') {"
            print '            GLint location = __glGetAttribLocationARB(programObj, name);'
            print '            if (location >= 0) {'
            bind_function = glapi.glapi.get_function_by_name('glBindAttribLocationARB')
            self.fake_call(bind_function, ['programObj', 'location', 'name'])
            print '            }'
            print '        }'
            print '    }'

        Tracer.trace_function_impl_body(self, function)

    gremedy_functions = [
        'glStringMarkerGREMEDY',
        'glFrameTerminatorGREMEDY',
    ]

    def dispatch_function(self, function):
        if function.name in ('glLinkProgram', 'glLinkProgramARB'):
            # These functions have been dispatched already
            return

        # We implement the GREMEDY extensions, not the driver
        if function.name in self.gremedy_functions:
            return

        if function.name in ('glXGetProcAddress', 'glXGetProcAddressARB', 'wglGetProcAddress'):
            if_ = 'if'
            for gremedy_function in self.gremedy_functions:
                print '    %s (strcmp("%s", (const char *)%s) == 0) {' % (if_, gremedy_function, function.args[0].name)
                print '        __result = (%s)&%s;' % (function.type, gremedy_function)
                print '    }'
                if_ = 'else if'
            print '    else {'
            Tracer.dispatch_function(self, function)
            print '    }'
            return

        # Override GL extensions
        if function.name in ('glGetString', 'glGetIntegerv', 'glGetStringi'):
            Tracer.dispatch_function(self, function, prefix = 'gltrace::__', suffix = '_override')
            return

        Tracer.dispatch_function(self, function)

    def emit_memcpy(self, dest, src, length):
        print '        unsigned __call = Trace::localWriter.beginEnter(&Trace::memcpy_sig);'
        print '        Trace::localWriter.beginArg(0);'
        print '        Trace::localWriter.writeOpaque(%s);' % dest
        print '        Trace::localWriter.endArg();'
        print '        Trace::localWriter.beginArg(1);'
        print '        Trace::localWriter.writeBlob(%s, %s);' % (src, length)
        print '        Trace::localWriter.endArg();'
        print '        Trace::localWriter.beginArg(2);'
        print '        Trace::localWriter.writeUInt(%s);' % length
        print '        Trace::localWriter.endArg();'
        print '        Trace::localWriter.endEnter();'
        print '        Trace::localWriter.beginLeave(__call);'
        print '        Trace::localWriter.endLeave();'
       
    buffer_targets = [
        'ARRAY_BUFFER',
        'ELEMENT_ARRAY_BUFFER',
        'PIXEL_PACK_BUFFER',
        'PIXEL_UNPACK_BUFFER',
    ]

    def wrap_ret(self, function, instance):
        Tracer.wrap_ret(self, function, instance)

            
        if function.name in ('glMapBuffer', 'glMapBufferARB'):
            print '    struct buffer_mapping *mapping = get_buffer_mapping(target);'
            print '    if (mapping) {'
            print '        mapping->map = %s;' % (instance)
            print '        mapping->length = 0;'
            print '        __glGetBufferParameteriv(target, GL_BUFFER_SIZE, &mapping->length);'
            print '        mapping->write = (access != GL_READ_ONLY);'
            print '        mapping->explicit_flush = false;'
            print '    }'

        if function.name == 'glMapBufferRange':
            print '    struct buffer_mapping *mapping = get_buffer_mapping(target);'
            print '    if (mapping) {'
            print '        mapping->map = %s;' % (instance)
            print '        mapping->length = length;'
            print '        mapping->write = access & GL_MAP_WRITE_BIT;'
            print '        mapping->explicit_flush = access & GL_MAP_FLUSH_EXPLICIT_BIT;'
            print '    }'

    boolean_names = [
        'GL_FALSE',
        'GL_TRUE',
    ]

    def gl_boolean(self, value):
        return self.boolean_names[int(bool(value))]

    # Names of the functions that unpack from a pixel buffer object.  See the
    # ARB_pixel_buffer_object specification.
    unpack_function_names = set([
        'glBitmap',
        'glColorSubTable',
        'glColorTable',
        'glCompressedTexImage1D',
        'glCompressedTexImage2D',
        'glCompressedTexImage3D',
        'glCompressedTexSubImage1D',
        'glCompressedTexSubImage2D',
        'glCompressedTexSubImage3D',
        'glConvolutionFilter1D',
        'glConvolutionFilter2D',
        'glDrawPixels',
        'glMultiTexImage1DEXT',
        'glMultiTexImage2DEXT',
        'glMultiTexImage3DEXT',
        'glMultiTexSubImage1DEXT',
        'glMultiTexSubImage2DEXT',
        'glMultiTexSubImage3DEXT',
        'glPixelMapfv',
        'glPixelMapuiv',
        'glPixelMapusv',
        'glPolygonStipple',
        'glSeparableFilter2D',
        'glTexImage1D',
        'glTexImage1DEXT',
        'glTexImage2D',
        'glTexImage2DEXT',
        'glTexImage3D',
        'glTexImage3DEXT',
        'glTexSubImage1D',
        'glTexSubImage1DEXT',
        'glTexSubImage2D',
        'glTexSubImage2DEXT',
        'glTexSubImage3D',
        'glTexSubImage3DEXT',
        'glTextureImage1DEXT',
        'glTextureImage2DEXT',
        'glTextureImage3DEXT',
        'glTextureSubImage1DEXT',
        'glTextureSubImage2DEXT',
        'glTextureSubImage3DEXT',
    ])

    def dump_arg_instance(self, function, arg):
        if function.name in self.draw_function_names and arg.name == 'indices':
            print '    GLint __element_array_buffer = 0;'
            print '    __glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING, &__element_array_buffer);'
            print '    if (!__element_array_buffer) {'
            if isinstance(arg.type, stdapi.Array):
                print '        Trace::localWriter.beginArray(%s);' % arg.type.length
                print '        for(GLsizei i = 0; i < %s; ++i) {' % arg.type.length
                print '            Trace::localWriter.beginElement();'
                print '            Trace::localWriter.writeBlob(%s[i], count[i]*__gl_type_size(type));' % (arg.name)
                print '            Trace::localWriter.endElement();'
                print '        }'
                print '        Trace::localWriter.endArray();'
            else:
                print '        Trace::localWriter.writeBlob(%s, count*__gl_type_size(type));' % (arg.name)
            print '    } else {'
            Tracer.dump_arg_instance(self, function, arg)
            print '    }'
            return

        # Recognize offsets instead of blobs when a PBO is bound
        if function.name in self.unpack_function_names \
           and (isinstance(arg.type, stdapi.Blob) \
                or (isinstance(arg.type, stdapi.Const) \
                    and isinstance(arg.type.type, stdapi.Blob))):
            print '    {'
            print '        GLint __unpack_buffer = 0;'
            print '        __glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING, &__unpack_buffer);'
            print '        if (__unpack_buffer) {'
            print '            Trace::localWriter.writeOpaque(%s);' % arg.name
            print '        } else {'
            Tracer.dump_arg_instance(self, function, arg)
            print '        }'
            print '    }'
            return

        # Several GL state functions take GLenum symbolic names as
        # integer/floats; so dump the symbolic name whenever possible
        if function.name.startswith('gl') \
           and arg.type in (glapi.GLint, glapi.GLfloat) \
           and arg.name == 'param':
            assert arg.index > 0
            assert function.args[arg.index - 1].name == 'pname'
            assert function.args[arg.index - 1].type == glapi.GLenum
            print '    if (is_symbolic_pname(pname) && is_symbolic_param(%s)) {' % arg.name
            dump_instance(glapi.GLenum, arg.name)
            print '    } else {'
            Tracer.dump_arg_instance(self, function, arg)
            print '    }'
            return

        Tracer.dump_arg_instance(self, function, arg)

    def footer(self, api):
        Tracer.footer(self, api)

        # A simple state tracker to track the pointer values
        # update the state
        print 'static void __trace_user_arrays(GLuint maxindex)'
        print '{'

        for camelcase_name, uppercase_name in self.arrays:
            function_name = 'gl%sPointer' % camelcase_name
            enable_name = 'GL_%s_ARRAY' % uppercase_name
            binding_name = 'GL_%s_ARRAY_BUFFER_BINDING' % uppercase_name
            function = api.get_function_by_name(function_name)

            print '    // %s' % function.name
            self.array_prolog(api, uppercase_name)
            print '    if (__glIsEnabled(%s)) {' % enable_name
            print '        GLint __binding = 0;'
            print '        __glGetIntegerv(%s, &__binding);' % binding_name
            print '        if (!__binding) {'

            # Get the arguments via glGet*
            for arg in function.args:
                arg_get_enum = 'GL_%s_ARRAY_%s' % (uppercase_name, arg.name.upper())
                arg_get_function, arg_type = TypeGetter().visit(arg.type)
                print '            %s %s = 0;' % (arg_type, arg.name)
                print '            __%s(%s, &%s);' % (arg_get_function, arg_get_enum, arg.name)
            
            arg_names = ', '.join([arg.name for arg in function.args[:-1]])
            print '            size_t __size = __%s_size(%s, maxindex);' % (function.name, arg_names)

            # Update the region
            print '            Trace::localWriter.updateRegion((const void *)pointer, __size);'
            print '        }'
            print '    }'
            self.array_epilog(api, uppercase_name)
            print

        # Samething, but for glVertexAttribPointer*
        #
        # Some variants of glVertexAttribPointer alias conventional and generic attributes:
        # - glVertexAttribPointer: no
        # - glVertexAttribPointerARB: implementation dependent
        # - glVertexAttribPointerNV: yes
        #
        # This means that the implementations of these functions do not always
        # alias, and they need to be considered independently.
        #
        print '    vertex_attrib __vertex_attrib = __get_vertex_attrib();'
        print
        for suffix in ['', 'ARB', 'NV']:
            if suffix:
                SUFFIX = '_' + suffix
            else:
                SUFFIX = suffix
            function_name = 'glVertexAttribPointer' + suffix
            print '    // %s' % function_name
            print '    if (__vertex_attrib == VERTEX_ATTRIB%s) {' % SUFFIX
            if suffix == 'NV':
                print '        GLint __max_vertex_attribs = 16;'
            else:
                print '        GLint __max_vertex_attribs = 0;'
                print '        __glGetIntegerv(GL_MAX_VERTEX_ATTRIBS, &__max_vertex_attribs);'
            print '        for (GLint index = 0; index < __max_vertex_attribs; ++index) {'
            print '            GLint __enabled = 0;'
            if suffix == 'NV':
                print '            __glGetIntegerv(GL_VERTEX_ATTRIB_ARRAY0_NV + index, &__enabled);'
            else:
                print '            __glGetVertexAttribiv%s(index, GL_VERTEX_ATTRIB_ARRAY_ENABLED%s, &__enabled);' % (suffix, SUFFIX)
            print '            if (__enabled) {'
            print '                GLint __binding = 0;'
            if suffix != 'NV':
                # It doesn't seem possible to use VBOs with NV_vertex_program.
                print '                __glGetVertexAttribiv%s(index, GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING%s, &__binding);' % (suffix, SUFFIX)
            print '                if (!__binding) {'

            function = api.get_function_by_name(function_name)

            # Get the arguments via glGet*
            for arg in function.args[1:]:
                if suffix == 'NV':
                    arg_get_enum = 'GL_ATTRIB_ARRAY_%s%s' % (arg.name.upper(), SUFFIX)
                else:
                    arg_get_enum = 'GL_VERTEX_ATTRIB_ARRAY_%s%s' % (arg.name.upper(), SUFFIX)
                arg_get_function, arg_type = TypeGetter('glGetVertexAttrib', False, suffix).visit(arg.type)
                print '                    %s %s = 0;' % (arg_type, arg.name)
                print '                    __%s(index, %s, &%s);' % (arg_get_function, arg_get_enum, arg.name)
            
            arg_names = ', '.join([arg.name for arg in function.args[1:-1]])
            print '                    size_t __size = __%s_size(%s, maxindex);' % (function.name, arg_names)

            # Emit a fake function
            print '                    unsigned __call = Trace::localWriter.beginEnter(&__%s_sig);' % (function.name,)
            for arg in function.args:
                assert not arg.output
                print '                    Trace::localWriter.beginArg(%u);' % (arg.index,)
                if arg.name != 'pointer':
                    dump_instance(arg.type, arg.name)
                else:
                    print '                    Trace::localWriter.writeBlob((const void *)%s, __size);' % (arg.name)
                print '                    Trace::localWriter.endArg();'
            
            print '                    Trace::localWriter.endEnter();'
            print '                    Trace::localWriter.beginLeave(__call);'
            print '                    Trace::localWriter.endLeave();'
            print '                }'
            print '            }'
            print '        }'
            print '    }'
            print

        print '}'
        print

    #
    # Hooks for glTexCoordPointer, which is identical to the other array
    # pointers except the fact that it is indexed by glClientActiveTexture.
    #

    def array_prolog(self, api, uppercase_name):
        if uppercase_name == 'TEXTURE_COORD':
            print '    GLint client_active_texture = 0;'
            print '    __glGetIntegerv(GL_CLIENT_ACTIVE_TEXTURE, &client_active_texture);'
            print '    GLint max_texture_coords = 0;'
            print '    __glGetIntegerv(GL_MAX_TEXTURE_COORDS, &max_texture_coords);'
            print '    for (GLint unit = 0; unit < max_texture_coords; ++unit) {'
            print '        GLint texture = GL_TEXTURE0 + unit;'
            print '        __glClientActiveTexture(texture);'

    def array_epilog(self, api, uppercase_name):
        if uppercase_name == 'TEXTURE_COORD':
            print '    }'
        self.array_cleanup(api, uppercase_name)

    def array_cleanup(self, api, uppercase_name):
        if uppercase_name == 'TEXTURE_COORD':
            print '    __glClientActiveTexture(client_active_texture);'
        
    def fake_call(self, function, args):
        print '            unsigned __fake_call = Trace::localWriter.beginEnter(&__%s_sig);' % (function.name,)
        for arg, instance in zip(function.args, args):
            assert not arg.output
            print '            Trace::localWriter.beginArg(%u);' % (arg.index,)
            dump_instance(arg.type, instance)
            print '            Trace::localWriter.endArg();'
        print '            Trace::localWriter.endEnter();'
        print '            Trace::localWriter.beginLeave(__fake_call);'
        print '            Trace::localWriter.endLeave();'











