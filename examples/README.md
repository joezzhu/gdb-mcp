# Examples

Sample program and scripts for testing the GDB MCP Server.

## Files

- `sample_program.c` — Multi-threaded C program (threads, mutex, shared counter)
- `Makefile` — Build with `make`
- `setup.gdb` — GDB initialization script example

## Build

```bash
cd examples
make
```

## Usage with AI

### Local Debugging

```
Start a GDB session with examples/sample_program,
set a breakpoint at main, run and tell me about the threads.
```

### Remote Debugging (SSH)

```
Debug examples/sample_program on server devbox:
1. Set breakpoint at worker_thread
2. Run the program
3. Show me what each thread is doing
```

### Core Dump Analysis

```bash
# Generate a core dump
ulimit -c unlimited
./sample_program &
kill -SEGV $!
```

```
Load the executable examples/sample_program and core dump core.XXXX,
tell me how many threads were running and what caused the crash.
```

## Example Prompts

**Thread analysis:**
```
Load examples/sample_program and tell me:
1. How many threads does it create?
2. What functions do the threads execute?
3. Which threads are waiting on mutexes?
```

**Conditional breakpoint:**
```
Debug examples/sample_program, set a breakpoint at worker_thread
only when counter > 5, run and show me the variables.
```

**Step-by-step:**
```
Debug examples/sample_program:
1. Break at main
2. Run to breakpoint
3. Step through 10 lines
4. Tell me the counter value
```

## Common Patterns

1. **Find and Fix**: Run → crash → backtrace → inspect variables → set earlier breakpoint → restart
2. **Thread Investigation**: Run → interrupt → get threads → backtrace each → inspect interesting ones
3. **Post-Mortem**: Load core → threads → crashed thread stack → global state → reconstruct events
4. **Sysroot Debugging**: Load with `core` param + `init_commands=["set sysroot /path"]`
