# Installing direnv on macOS

[direnv](https://direnv.net/) loads the project's `.envrc` automatically when you `cd`
into the repo. In this project it adds `scripts/bin` to your `PATH`, so the helper
scripts can be run by name.

## Requirements

- [Homebrew](https://brew.sh/)

## 1. Install

```bash
brew install direnv
```

## 2. Hook direnv into your shell

zsh is the default shell on macOS. Add this line to the **end** of `~/.zshrc`:

```bash
eval "$(direnv hook zsh)"
```

If you use bash instead, add this to the end of `~/.bash_profile`:

```bash
eval "$(direnv hook bash)"
```

Then open a new terminal window, or reload your config:

```bash
source ~/.zshrc
```

## 3. Allow the project's `.envrc`

```bash
cd path/to/junctionX
direnv allow
```

direnv won't load an `.envrc` until you approve it. You'll need to run `direnv allow`
again whenever `.envrc` changes.

## 4. Verify

When you `cd` into the repo, you should see:

```text
direnv: loading .../junctionX/.envrc
```

Check that `scripts/bin` is on your `PATH`:

```bash
echo "$PATH" | tr ':' '\n' | head -1
```

It should print the path to the repo's `scripts/bin` directory.

## Troubleshooting

- **Nothing happens on `cd`:** the hook isn't loaded. Make sure the `eval` line is in
  the right file for your shell (`echo $SHELL` tells you which shell you use), then open
  a new terminal.
- **`direnv: error .envrc is blocked`:** run `direnv allow`.
- **Hook doesn't take effect:** the `eval` line must come **after** anything else that
  changes your prompt or `PATH` (oh-my-zsh, pyenv, conda, etc.).
- **VS Code extensions or the debugger don't see the environment:** launch VS Code
  from a terminal inside the repo (`code .`), or install the
  [direnv extension](https://marketplace.visualstudio.com/items?itemName=mkhl.direnv).
- **A script in `scripts/bin` gives `command not found` or `permission denied`:** make
  sure it's executable (`chmod +x scripts/bin/<name>`) and starts with a shebang such as
  `#!/usr/bin/env bash`.
