import secrets
from pathlib import Path

import torch.nn
import yaml

from .config import PerthConfig


class CheckpointManager:
    def __init__(self, models_dir, run_name, dataset_hp: PerthConfig=None):
        self.save_path = Path(models_dir) / run_name
        self.save_path.mkdir(exist_ok=True, parents=True)

        self.hparams_file = self.save_path.joinpath("hparams.yaml")
        if self.hparams_file.exists():
            self.hp = self.load_hparams()
            if dataset_hp is not None:
                assert self.hp == dataset_hp
        else:
            assert dataset_hp is not None
            self.hp = dataset_hp
            self.save_hparams()

        self.id_file = self.save_path.joinpath("id.txt")
        if self.id_file.exists():
            self.id = self.id_file.read_text()
        else:
            self.id = secrets.token_urlsafe(16)
            self.id_file.write_text(self.id)

    def load_latest(self, ext=".pth.tar"):
        sortkey = lambda x: int(x.name.replace(ext, "").split("_")[-1])
        ckpts = sorted([p for p in self.save_path.iterdir() if p.name.endswith(ext)], key=sortkey)
        if any(ckpts):
            return torch.load(ckpts[-1], map_location="cpu")

    def load_hparams(self):
        with self.hparams_file.open("r") as hp_file:
            return PerthConfig(**yaml.load(hp_file, Loader=yaml.FullLoader))

    def save_hparams(self):
        with self.hparams_file.open("w") as hparams_file:
            hparams_file.write(yaml.dump(self.hp._asdict()))

    def save_model(self, model, step):
        state = {
            "model": model.state_dict() if isinstance(model, torch.nn.Module) else model,
            "step": step,
        }
        basename = f"perth_net_{step:06d}"
        checkpoint_fpath = Path(self.save_path, f"{basename}.pth.tar")
        try:
            torch.save(state, checkpoint_fpath)
        except KeyboardInterrupt:
            if checkpoint_fpath.exists():
                checkpoint_fpath.unlink()
