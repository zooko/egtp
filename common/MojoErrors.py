import exceptions

# throws by anything which doesn't like what was passed to it
class DataError(exceptions.StandardError):
    pass

# thrown by MojoMessage
class MojoMessageError(DataError):
    pass

# thrown by DataTypes
class BadFormatError(DataError):
    pass

# throws by things which do block reassembly
class ReassemblyError(IOError):
    pass

