## Build GnWManager with debugging symbols
```
make clean
DEBUG=1 make
```

## Dropping into debugger.
Press the power button and enter the following at the same time:
```
gnwmanager debug gdb
```


## Common GDB Commands
After dropping into the debugger, it'd be common to set a breakpoint.

```
(gdb) break Core/Src/main.c:main
```
