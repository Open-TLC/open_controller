from typing import Any

import gymnasium
import gymnasium as gym
import torch
from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.core.columns import Columns
from ray.rllib.models.torch.torch_modelv2 import TorchModelV2
from ray.rllib.utils.typing import ModelConfigDict, TensorType
from torch import nn
from torch.distributions import Categorical


class FRAPMaskedPPORLModule(DefaultPPOTorchRLModule):
    """RL module built with FRAP architecture.

    FRAP calculates embeddings for all phases based on their features (i.e. demand),
    and then compares phases with one another based on those embeddings.
    """

    def setup(self):
        """Create and initialize the module."""
        # Extract action space dimensions.
        if isinstance(self.action_space, gym.spaces.Discrete):
            self.num_phases = self.action_space.n
        else:
            raise ValueError(
                f"Expected Discrete action space, got {type(self.action_space)}",
            )

        # Custom hyperparams passed via model_config
        hidden_dim = self.model_config.get("hidden_dim", 32)
        embed_dim = self.model_config.get("embed_dim", 16)

        phase_feat_dim = 4  # Adjust according to your real_obs shape

        # Phase encoder creates embeddings that describe the features of phases. These
        # embeddings can then be used to compare priorities of different phases.
        # Input features per phase: [phase_pressure, is_active, duration, phase_transit]
        self.phase_encoder = nn.Sequential(
            nn.Linear(phase_feat_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, embed_dim),
            nn.ReLU(),
        )

        # Competition network takes two demand embeddings and compares them.
        self.competition_network = nn.Sequential(
            nn.Linear(embed_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

        # Critic network for the agent.
        self.value_head = nn.Sequential(
            nn.Linear(self.num_phases * embed_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def compute_values(self, batch: dict, embeddings=None) -> torch.Tensor:
        """Calculate critic values from observation."""
        obs = batch[Columns.OBS]
        real_obs = obs["real_obs"].float()
        batch_size = real_obs.shape[0]

        phase_embeddings = self.phase_encoder(real_obs)
        flat_context = phase_embeddings.view(batch_size, -1)
        vf_preds = self.value_head(flat_context).squeeze(-1)

        if vf_preds.ndim == 0:
            vf_preds = vf_preds.unsqueeze(0)

        return vf_preds

    def get_initial_state(self) -> dict:
        """Return empty state, as the module is stateless."""
        return {}

    def is_stateful(self) -> bool:
        """Explicitly flag the module as stateless."""
        return False

    def _forward(self, batch: dict, **kwargs) -> dict:
        obs = batch[Columns.OBS]
        real_obs = obs["real_obs"].float()
        action_mask = obs["action_mask"].float()
        batch_size = real_obs.shape[0]

        # Phase feature embeddings are calculated for all phases.
        phase_embeddings = self.phase_encoder(real_obs)

        flat_context = phase_embeddings.view(batch_size, -1)
        vf_preds = self.value_head(flat_context).squeeze(-1)

        # Ensure that prediction remains in right dimensions
        # even with batch size (phase count) == 1.
        if vf_preds.ndim == 0:
            vf_preds = vf_preds.unsqueeze(0)

        # Phase pairs are built from all phase embeddings.
        h_i = phase_embeddings.unsqueeze(2).expand(
            batch_size,
            self.num_phases,
            self.num_phases,
            -1,
        )
        h_j = phase_embeddings.unsqueeze(1).expand(
            batch_size,
            self.num_phases,
            self.num_phases,
            -1,
        )

        # Embeddings on all phase pairs are concatenated.
        pair_features = torch.cat([h_i, h_j], dim=-1)

        # Competion matrix is calculated from phase pairings. The matrix now consists
        # of priority scores of phase_x vs phase_y.
        competition_matrix = self.competition_network(pair_features).squeeze(-1)

        # Priority scores are summed across columns to get the final logits.
        raw_logits = competition_matrix.sum(dim=-1)

        # Action mask is applied to the final logits.
        inf_mask = (1.0 - action_mask) * -1e8
        masked_logits = raw_logits + inf_mask

        return {
            Columns.ACTION_DIST_INPUTS: masked_logits,
            Columns.VF_PREDS: vf_preds,
        }

    def _forward_exploration(self, batch: dict, **kwargs) -> dict:
        outs = self._forward(batch, **kwargs)
        logits = outs[Columns.ACTION_DIST_INPUTS]
        dist = Categorical(logits=logits)
        actions = dist.sample()

        outs[Columns.ACTIONS] = actions
        outs[Columns.ACTION_LOGP] = dist.log_prob(actions)
        return outs

    def _forward_inference(self, batch: dict, **kwargs) -> dict:
        outs = self._forward(batch, **kwargs)
        logits = outs[Columns.ACTION_DIST_INPUTS]
        actions = torch.argmax(logits, dim=-1)
        dist = Categorical(logits=logits)

        outs[Columns.ACTIONS] = actions
        outs[Columns.ACTION_LOGP] = dist.log_prob(actions)
        return outs

    def _forward_train(self, batch: dict, **kwargs) -> dict:
        outs = self._forward(batch, **kwargs)
        logits = outs[Columns.ACTION_DIST_INPUTS]
        dist = Categorical(logits=logits)

        if Columns.ACTIONS in batch:
            outs[Columns.ACTION_LOGP] = dist.log_prob(batch[Columns.ACTIONS])
        return outs


class FRAPMaskedPPOModel(TorchModelV2, nn.Module):
    """Custom PyTorch model for RLlib PPO using the FRAP phase competition."""

    def __init__(
        self,
        obs_space: gymnasium.Space,
        action_space: gymnasium.Space,
        num_outputs: int,
        model_config: ModelConfigDict,
        name: str,
    ) -> None:
        """Initialize the FRAPMaskedPPOModel neural network layers and configurations.

        Args:
            obs_space: Observation space dictionary containing real observation and an
                action mask.
            action_space: Action space of the agent. Each discrete option represents
                a possible phase.
            num_outputs: Number of possible phases.
            model_config: RLlib model configuration dictionary.
            name: RLlib model name.

        Raises:
            TypeError: If `obs_space` (or its wrapped `original_space`) is not a
                `gymnasium.spaces.Dict` or if 'real_obs' is not a
                `gymnasium.spaces.Box`.

        """
        TorchModelV2.__init__(
            self,
            obs_space,
            action_space,
            num_outputs,
            model_config,
            name,
        )
        nn.Module.__init__(self)

        self.num_phases: int = num_outputs

        dict_space: gymnasium.spaces.Space = getattr(
            obs_space,
            "original_space",
            obs_space,
        )
        if not isinstance(dict_space, gymnasium.spaces.Dict):
            raise TypeError(
                "Expected observation space to be gymnasium.spaces.Dict, got "
                f"{type(dict_space)}",
            )

        real_obs_space: gymnasium.spaces.Space = dict_space["real_obs"]
        if not isinstance(real_obs_space, gymnasium.spaces.Box):
            raise TypeError(
                "Expected 'real_obs' to be gymnasium.spaces.Box, got "
                f"{type(real_obs_space)}",
            )

        # Custom network specific configurations.
        custom_config: dict[str, Any] = model_config.get("custom_model_config", {})

        hidden_dim: int = custom_config.get("hidden_dim", 32)
        embed_dim: int = custom_config.get("embed_dim", 16)

        # Phase encoder creates embeddings that describe the features of phases. These
        # embeddings can then be used to compare priorities of different phases.
        # Input features per phase: [phase_pressure, is_active, duration, phase_transit]
        phase_feat_dim = 4
        self.phase_encoder: nn.Sequential = nn.Sequential(
            nn.Linear(phase_feat_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, embed_dim),
            nn.ReLU(),
        )

        # Competition network takes two demand embeddings and compares them.
        self.competition_network: nn.Sequential = nn.Sequential(
            nn.Linear(embed_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

        # Critic network for the agent.
        self.value_head: nn.Sequential = nn.Sequential(
            nn.Linear(self.num_phases * embed_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

        self._current_value: torch.Tensor | None = None

    def forward(
        self,
        input_dict: dict[str, Any],
        state: list[TensorType],
        seq_lens: TensorType,
    ) -> tuple[torch.Tensor, list[TensorType]]:
        real_obs = input_dict["obs"]["real_obs"].float()
        action_mask = input_dict["obs"]["action_mask"].float()
        batch_size = real_obs.shape[0]

        # Phase feature embeddings are calculated for all phases.
        phase_embeddings = self.phase_encoder(real_obs)

        # Critic network calculates the state value.
        flat_context = phase_embeddings.view(batch_size, -1)
        self._current_value = self.value_head(flat_context).squeeze(-1)

        # Phase pairs are built from all phase embeddings.
        h_i = phase_embeddings.unsqueeze(2).expand(
            batch_size,
            self.num_phases,
            self.num_phases,
            -1,
        )
        h_j = phase_embeddings.unsqueeze(1).expand(
            batch_size,
            self.num_phases,
            self.num_phases,
            -1,
        )

        # Embeddings on all phase pairs are concatenated.
        pair_features = torch.cat([h_i, h_j], dim=-1)

        # Competion matrix is calculated from phase pairings. The matrix now consists
        # of priority scores of phase_x vs phase_y.
        competition_matrix = self.competition_network(pair_features).squeeze(-1)

        # Priority scores are summed across columns to get the final logits.
        raw_logits = competition_matrix.sum(dim=-1)

        # Action mask is applied to the final logits.
        inf_mask = (1.0 - action_mask) * -1e8
        masked_logits = raw_logits + inf_mask

        return masked_logits, state

    def value_function(self) -> torch.Tensor:
        if self._current_value is None:
            raise ValueError("forward() must be called before value_function()")
        return self._current_value
