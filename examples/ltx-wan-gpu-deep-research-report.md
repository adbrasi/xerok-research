# GPUs, aluguel e serverless para vídeo com LTX 2.x e WAN — guia de decisão com benchmarks (2026)

## Sumário Executivo

1. **LTX-2.3 é o caminho de menor custo e maior velocidade hoje.** No mesmo RTX 4090, LTX-2.3 roda em ~1–2 min/clipe contra 12–18 min/clipe da WAN 2.2 — uma razão de **10–14×** [1]. No RTX 5090, LTX-2.3 GGUF Q4 gera um clipe I2V de 81 frames em **22,1 s**, ~**5,7× mais rápido** que a WAN 2.2 14B GGUF [2].
2. **A placa custo-benefício para uso diário é a RTX 4090 (24 GB) para LTX, e a RTX 5090 (32 GB) quando você quer throughput por dólar.** A 5090 é **~45% mais rápida** em image-to-video (≈7 min vs ≈12,7 min por job WAN 2.1) [3] e tem **1.792 GB/s** de banda (+78% sobre os 1.008 GB/s da 4090) [4]. WAN em 720p exige H100/80 GB; LTX-2.3 cabe em 24 GB com FP8 [5].
3. **O aluguel por hora mais barato é a Salad** (RTX 4090 **$0,18/h**, RTX 5090 **$0,27/h**) [6], seguida por RunPod Community (~$0,34/h) [7] e Vast.ai ($0,29–0,39/h) [8] — mas o preço baixo da Salad/Vast vem com confiabilidade de spot, não SLA.
4. **Para gerar vídeo, alugar por hora vence serverless.** O serverless da RunPod cobra um prêmio de **~66%** sobre o pod por hora no mesmo H100 ($4,47/h vs $2,69/h) [9], e só compensa abaixo de ~40% de utilização. Pior: o **timeout padrão de job no RunPod Serverless é 600 s** e mata renders longos [10].
5. **"10 minutos de LTX 2.3 em um render" é uma premissa falsa.** A geração nativa da LTX-2.3 satura em **~20 s** (Fast) / ~10 s (Pro) [11]; 10 minutos exigem **stitching/extensão** de dezenas de clipes, não uma geração única.
6. **As otimizações de ComfyUI são reais, mas têm armadilhas.** SageAttention entrega **2,1–3,9×** sobre FlashAttention [12][13], mas dá **0% de ganho sobre LTX-2.3 em GGUF** [2]; FP8 é o nível seguro (~98% SSIM) [14]; NVFP4 só acelera em Blackwell e hoje está **quebrado no ComfyUI** (faz upcast para fp16/fp8 e estoura VRAM) [15].
7. **Caminho recomendado para produção diária:** LTX-2.3 em **FP8** num **RTX 4090 (community/spot) ou RTX 5090** com **SageAttention + torch.compile**, alugado por hora na Salad/RunPod Community/Vast (filtrando confiabilidade), com checkpoint de progresso — não serverless, exceto para tráfego de API esporádico.

## Escopo

### O que este relatório estabelece
Comparação de **GPUs** (specs, VRAM, velocidade) para os modelos de vídeo **LTX 2.x** e **WAN**, **preços de aluguel por hora** (RunPod, Vast.ai, Novita, Salad), **plataformas serverless** (RunPod Serverless, Modal, Beam, Fal, Replicate), o trade-off **serverless vs por hora/spot**, o caminho prático para **vídeos longos com LTX-2.3**, e as **otimizações de velocidade do ComfyUI** (SageAttention, Nunchaku/SVDQuant, FP8/NVFP4/GGUF, TeaCache, torch.compile), com benchmarks datados e fontes primárias.

### O que este relatório NÃO estabelece
- **Não** há benchmark público de geração contínua de **10 minutos** de LTX-2.3; todos os números de "10 min" são **extrapolações** de clipes curtos [16] e dependem de workflow de stitching ainda **não documentado** quanto a coerência de emendas.
- **Não** medimos qualidade perceptual de forma padronizada; números de SSIM/LPIPS vêm de fontes terceiras e medições isoladas [14][17].
- Preços de GPU em marketplaces (Vast.ai, RunPod Community, Salad) **flutuam por hora** e por host; os valores aqui são instantâneos de junho/2026 e devem ser reconferidos antes de comprar.

### Desambiguação de entidades
| Termo | Resolução canônica | Base/observação |
|---|---|---|
| LTX 2.x / "2.3+" | **LTX-2.3** (Lightricks, 25/mar/2026, DiT 22B) [18] | máx. nativo ~20 s; requisito oficial 32 GB, prático 24 GB com FP8 [5] |
| WAN | família **Wan-Video** (Alibaba): WAN 2.2 (27B MoE, jul/2025) [19], WAN 2.5 (set/2025, **fechada/API**) [20], WAN 2.7 (abr/2026, aberta) [21] | 720p exige ~65–80 GB em FP16 [5] |
| Quant "sem perda" | **FP8** (~98% SSIM, seguro) [14]; **NVFP4/INT4** (Blackwell, troca fidelidade por velocidade) [17] | "sem perda" é impreciso: todo 4-bit degrada |
| "Serverless" | scale-to-zero, cobrança por segundo (RunPod Serverless, Modal, Beam, Fal) | ≠ "pod por hora"; carrega prêmio e timeouts [9][10] |
| "Spot/community/interruptível" | tiers de baixo custo **sem SLA**, com interrupção [22][23] | exige checkpoint/resume |

## 1. GPUs: specs, VRAM e velocidade (sub-pergunta 1)

Para difusão de vídeo o gargalo é a **atenção** (custo O(L²) sobre uma sequência de latentes de 10K–100K tokens por clipe curto) e a **banda de memória**, não só a capacidade de VRAM [24][4]. Isso explica por que a Blackwell se destaca.

| GPU | VRAM / Banda | Destaque p/ LTX/WAN | Velocidade medida |
|---|---|---|---|
| **RTX 4090** (Ada) | 24 GB / 1.008 GB/s | sweet spot LTX-2.3 1080p (FP8) [25] | LTX-2.3 ~1–2 min/clipe [1]; WAN 2.2 ~7 s/frame @480p [26] |
| **RTX 5090** (Blackwell) | 32 GB / 1.792 GB/s, FP4 nativo [27] | melhor throughput/$; habilita NVFP4/SageAttn3 | ~45% mais rápida que 4090 (i2v) [3]; WAN 2.2 ~1 s/frame @720p [26] |
| **L40S** | 48 GB / 864 GB/s | quando o modelo passa de 24 GB | $0,79/h community RunPod [28] |
| **H100 80GB** | 80 GB / 3,35 TB/s | obrigatória p/ WAN 720p em FP16 [5] | WAN 2.2 40 steps em ~60 s (8×H100, otimizado) [29] |
| **RTX PRO 6000 / B200** | 96 GB / 180 GB | jobs muito grandes, serverless premium | $2,20/h e $5,50/h na Koyeb [30] |

**Leitura:** a diferença 4090→5090 vem de **FP4 nativo + 78% mais banda** [4]; a 4090 não tem caminho FP4 nativo (só emula, devagar), enquanto FP8 roda nativo nas duas [4]. Para **WAN em FP16** não há atalho de consumo: 720p pede H100 [5].

## 2. Preços de aluguel por hora por provedor (sub-pergunta 2)

| Provedor | RTX 4090 | RTX 5090 | H100 | Melhor custo-benefício |
|---|---|---|---|---|
| **Salad** | **$0,18/h** [6] | **$0,27/h** [6] | — | mais barato do mercado (spot-like) |
| **RunPod Community** | ~$0,34/h [7] | disponível | — | equilíbrio preço/UX |
| **RunPod Secure** | $0,69/h [31] | — | $2,89/h [31] | confiabilidade |
| **Vast.ai** (marketplace) | $0,29–0,39/h [8] | $0,32–0,52/h [32] | $1,47/h [8] | leilão; filtrar host |
| **Novita** | ~$0,35/h | — | $1,45/h on-demand; **$0,73/h spot** [33] | H100 spot barato |
| **Spheron (agregador)** | — | — | spot $1,03/h [34] | comparação multi-provider |

O **piso de spot** do RTX 4090 chega a ~$0,09/h na RunPod Community [7]. A escolha não é só preço: Vast.ai e Salad são **marketplaces/crowdsourced sem SLA** (ver §4 e Limitações).

## 3. Serverless comparado (sub-pergunta 3)

| Plataforma | Preço (por segundo → /h) | Cold start | Observação |
|---|---|---|---|
| **RunPod Serverless** | 4090 PRO $1,12/h; A100 $2,74/h; H100 $4,18/h [35] | FlashBoot: 48% <200 ms, resto até 60 s+ [9] | timeout padrão **600 s** [10]; nem sempre entrega "sub-segundo" [36] |
| **Modal** | H100 $3,95/h; A100 80GB $2,50/h [37] | container ~1 s, mas pesos grandes somam minutos [38] | snapshots cortam cold start de ~118 s p/ ~12 s [9] |
| **Beam** | — | típico 2–3 s [9] | foco em latência baixa |
| **Fal.ai** | L40S/A100 ~$0,99/h; Wan 2.5 $0,05/s de vídeo [39] | otimizado p/ mídia generativa | engine proprietária p/ difusão |
| **Replicate** | A100 $5,04/h; vídeo $0,07–0,25/s [40] | variável | conveniência via API |
| **Koyeb** | RTX PRO 6000 $2,20/h; B200 $5,50/h [30] | scale-to-zero | GPUs Blackwell grandes |

No mesmo H100, a RunPod Serverless ($4,47/h) custa **~6% menos** que a Modal ($4,76/h), e a RunPod é **~32% mais barata** que a Modal no tier A100 [9].

## 4. Serverless vs aluguel por hora/spot (sub-pergunta 4)

A regra é de **utilização**: serverless ganha quando a GPU fica ociosa a maior parte do tempo (tráfego de API esporádico, <~40% de uso); aluguel por hora ganha para **batch contínuo** como renderizar vídeo [5].

- **Prêmio de serverless:** H100 serverless RunPod ($4,47/h) é **66% mais caro** que o pod on-demand ($2,69/h) e **3× mais caro** que H100 spot na Novita ($0,73/h) [5]. Para um lote de 10 min de LTX (≈40–120 min de compute), o pod vence sempre [5].
- **Armadilhas de serverless:** timeout padrão de **600 s** que mata o job [10]; cold start real de minutos ao carregar pesos grandes (o "~1 s" da Modal é só o contêiner) [38]; cobrança contínua mesmo a 0% de GPU e por volumes parados (~$0,07/GB/mês) [41].
- **Armadilhas de spot:** desconto de **40–70%** [22], mas Vast.ai interrompe **sem aviso garantido** (≈15 s) [22][23] e a confiabilidade é **por host** (filtrar score >0,95) [42]; Salad é spot-like com **~90–95%** de uptime por nó e sem SLA [43]. Qualquer render longo precisa de **checkpoint/resume**.

## 5. Otimizações de ComfyUI e seus mecanismos (sub-pergunta 6)

**Atenção quantizada (maior alavanca).** SageAttention quantiza Q·Kᵀ para INT8 (com smoothing de outliers) e P·V em FP8, rodando em Tensor Cores INT8 — **2,1× sobre FlashAttention2** com perda quase nula [44]. Evolução: **SageAttention2++ → 3,9×** [13]; **SageAttention3** usa FP4 microscaling nos Tensor Cores da Blackwell, atingindo **1.038 TOPS e 5×** no RTX 5090 [45] — daí a vantagem da 5090 sobre a 4090, que não tem FP4 nativo. **Ressalva crítica:** sobre **LTX-2.3 em GGUF, o ganho do SageAttention é 0%** (a desquantização do GGUF vira o gargalo); só ajuda ~13% na WAN 2.2 GGUF [2].

**Quantização de pesos.** **SVDQuant/Nunchaku** roda 4-bit (W4A4) sem perda visível migrando outliers para um ramo low-rank em alta precisão e fundindo os kernels — **3,5× de memória e até 8,7–10,1×** end-to-end vs BF16 num 4090 de 16 GB (porque elimina o offload para CPU) [46][47]. Mas **NVFP4 é exclusivo da Blackwell**: 30/40-series caem para INT4 (pior) [48], e hoje o ComfyUI **falha em preservar o NVFP4 nativo**, fazendo upcast para fp16 (~28 GB → OOM) ou fp8 [15].

**Formatos — escada de velocidade/qualidade.** No B200, **NVFP4 dá 1,68× para LTX-2** (vs 1,19× do MXFP8), mas custa fidelidade (LPIPS 0,44 NVFP4 vs 0,11 MXFP8 no Flux) [17]; **FP8 é o nível seguro** (~98% SSIM na LTX-2.3) [14]; **GGUF é só armazenamento**, desquantiza on-the-fly, ganha VRAM mas **não** throughput (Q4 ~95% SSIM e **~20% mais lento** que FP16 no 4090) [14][49].

**Caching e compilação.** **TeaCache** dá ~2,8× na WAN 2.1 [50]; **torch.compile** (fusão de kernels + CUDA Graphs) soma até 1,81× em batch 1 [17]. Para caber vídeos longos, **block-swap** troca blocos GPU↔CPU (compra viabilidade ao custo de velocidade) [51].

## 6. Frontier: LTX 2.x e WAN recentes (sub-pergunta 7)

- **LTX-2.3** (25/mar/2026): DiT 22B, VAE reconstruída, 24/48 fps, 4K, clipes até 20 s; variante destilada em **8 steps**, FP8 em 23,5 GB e GGUF Q4 em 17,8 GB [18][2].
- **WAN 2.7** (abr/2026): MoE 27B/14B-ativo, 1080p até 15 s, **60 fps nativo**, Thinking Mode, texto em 12 idiomas, 4-em-1 [21]. **WAN 2.5** (set/2025) estreou forte mas **fechada/API** [20].
- **Aceleração WAN 2.2:** de 4,67 s → 1,51 s por step (**3,09×**) em 8×H100 com batched passes + SageAttention INT8 + TeaCache [29]; **FPSAttention** (FP8+sparsity) chega a **4,96× end-to-end** em 720p WAN 2.1 [52].
- **Hardware novo:** SageAttention 2.2.0 pré-compilado para Blackwell (~35% mais rápido) [53]; RTX PRO 6000 (96 GB) e B200 (180 GB) já em serverless [30].

## Análise Abrangente

### 1. Quais GPUs têm melhor custo-benefício para uso diário de LTX 2.x e WAN
Para **LTX-2.3**: **RTX 4090 (24 GB) em FP8** é o sweet spot diário [25]; suba para **RTX 5090** se quiser ~45% mais throughput e habilitar FP4/SageAttn3 [3]. Para **WAN em FP16/720p** não há placa de consumo, é **H100 80 GB** [5]; em consumo, só rodando WAN quantizada (GGUF Q4 ~8–18 GB) [49].

### 2. Melhores preços e a placa custo-benefício por provedor
Mais barato por hora: **Salad** (4090 $0,18/h, 5090 $0,27/h) [6]; **RunPod Community** 4090 ~$0,34/h [7]; **Vast.ai** 4090 $0,29–0,39/h [8]; **Novita** H100 spot $0,73/h [33]. A placa custo-benefício é a **RTX 4090** em quase todos, exceto na Salad onde a **5090 a $0,27/h** é imbatível em throughput/$.

### 3. Serverless comparado — quando cada um vence
**RunPod Serverless**: mais barato no H100/A100 e bom para API com FlashBoot [35][9]. **Modal**: melhor DX e snapshots de cold start, mas mais caro [37][9]. **Beam**: menor latência de cold start (2–3 s) [9]. **Fal**: melhor para mídia generativa pronta (preço por segundo de vídeo) [39]. **Replicate**: conveniência, preço alto [40]. Vencem só sob **baixa utilização**.

### 4. Serverless vs por hora/spot — qual o melhor caso
Use **serverless** apenas para tráfego **esporádico/imprevisível** (endpoint de API). Para **gerar vídeo em lote**, use **pod por hora** (ou spot com checkpoint): o serverless cobra ~66% de prêmio e impõe timeout de 600 s [9][10]. Spot/community corta 40–70% do custo [22] mas exige tolerância a interrupção [23].

### 5. Caminho recomendado para gerar 10 minutos de vídeo com LTX 2.3
Primeiro, **reenquadre a meta**: 10 min ≠ um render, LTX-2.3 satura em ~20 s nativos [11], então o pipeline é **gerar dezenas de clipes curtos + stitching/extensão**. Recomendação:
1. **Modelo/formato:** LTX-2.3 **FP8** (qualidade ~98% SSIM, cabe em 24 GB) [14][5]; evite GGUF para vídeo (mais lento e SageAttention não ajuda) [2].
2. **GPU:** **RTX 5090** para máxima velocidade (5,7× sobre WAN; FP4/SageAttn3) [2], ou **RTX 4090** para o menor custo [1].
3. **Onde:** **pod por hora** na Salad/RunPod Community/Vast (filtrando confiabilidade), **não** serverless; ~85–120 min de compute para 10 min de saída no 4090 [16], custo de compute na ordem de poucos dólares no tier $0,18–0,34/h [6][7].
4. **Otimização:** **SageAttention + torch.compile** (+ TeaCache) [12][17][50]; **checkpoint** cada clipe para sobreviver a interrupções de spot [23].

### 6. Otimizações de velocidade recentes no ComfyUI com benchmarks
Ver §5: SageAttention 2,1–3,9× [44][13] (0% em GGUF-LTX [2]), SVDQuant/Nunchaku até 8,7× [47], NVFP4 1,68× em Blackwell mas hoje quebrado no ComfyUI [17][15], FP8 seguro [14], TeaCache 2,8× [50], torch.compile 1,81× [17].

### 7. Patches e benchmarks recentes de LTX 2.x e WAN
Ver §6: LTX-2.3 (mar/2026) [18], WAN 2.7 (abr/2026, 60 fps) [21], WAN 2.5 fechada [20], aceleração WAN 2.2 3,09× [29] e FPSAttention 4,96× [52].

## Limitações e Ressalvas

**Frescor e variação de preço.** Preços de marketplace (Vast.ai, RunPod Community, Salad) flutuam por hora e por host; valores são instantâneos de jun/2026 e devem ser reconferidos. Alguns números de preço (Spheron, Markaicode) vêm de blogs terceiros, não de páginas de pricing ao vivo, confira em runpod.io/salad.com [41].

**Base de medição.** Benchmarks "até Nx" dependem de batch/resolução (ex.: ~83% em batch 1 vs ~396% em batch 16) [54], e o 4,96× do FPSAttention é específico de 720p/WAN 2.1 e *training-aware* [52]. SSIM de FP8/GGUF da LTX vem de uma única fonte terceira [14].

**A meta de 10 minutos.** Não há benchmark público de 10 min contínuos de LTX-2.3; tudo é extrapolado de clipes curtos [16], e a coerência de emendas no stitching é uma questão em aberto [11].

**Quantização não é gratuita.** "Sem perda" é impreciso: FP8 ~98% SSIM, GGUF Q4 ~95% com banding e ~20% mais lento [14]; NVFP4 troca fidelidade por velocidade (LPIPS 0,44) [17] e hoje está bugado no ComfyUI [15].

**Confiabilidade de spot/serverless.** Salad ~90–95% por nó sem SLA [43]; Vast.ai interrompe sem aviso garantido [23]; cold starts de serverless para modelos grandes são piores que o anunciado [38][36]. A reprodutibilidade desses números (especialmente Salad, cuja doc retornou 403) merece reverificação manual.

## Conclusão

Para uso diário de vídeo em 2026, o trade-off ótimo é **LTX-2.3 em FP8 num RTX 4090 (custo) ou RTX 5090 (velocidade), alugado por hora em provedor de baixo custo com checkpoint**, e **não** serverless, que só compensa para tráfego de API esporádico. WAN continua mais pesada (H100 para 720p em FP16), porém com forte ecossistema aberto (WAN 2.7) e ganhos de SageAttention/TeaCache. As otimizações do ComfyUI são decisivas, mas condicionais: **FP8 é o caminho seguro e portátil; NVFP4/Nunchaku só rendem na Blackwell e ainda têm arestas de tooling**; e o objetivo de "10 minutos" é, na prática, um pipeline de stitching, não um único render.

## Sources

[1] WaveSpeed, LTX-2.3 vs WAN 2.2: Open-Source Video Model Comparison (2026)
https://wavespeed.ai/blog/posts/ltx-2-3-vs-wan-2-2-comparison-2026/

[2] Zenn, LTX-2.3 22B vs Wan 2.2 14B: Benchmarking 5.7x Faster I2V on RTX 5090
https://zenn.dev/toki_mwc/articles/ltx23-vs-wan22-i2v-benchmark-rtx5090?locale=en

[3] Valdi AI, RTX 5090 vs 4090 in the Real World of Image-to-Video Inference
https://www.valdi.ai/blog/rtx-5090-vs-4090-in-the-real-world-of-image-to-video-inference

[4] Spheron, NVIDIA RTX 5090 Specs: 32GB GDDR7, Blackwell, 5th Gen Tensor Cores
https://www.spheron.network/blog/nvidia-rtx-5090-specs/

[5] RunPod, Serverless GPU Deployment vs. Pods for Your AI Workload
https://www.runpod.io/articles/comparison/serverless-gpu-deployment-vs-pods

[6] Salad Cloud, GPU Pricing
https://salad.com/pricing

[7] GetDeploying, RTX 4090 Cloud Pricing: Compare 14+ Providers (2026)
https://getdeploying.com/gpus/nvidia-rtx-4090

[8] Vast.ai, Rent RTX 4090 GPUs
https://vast.ai/pricing/gpu/RTX-4090

[9] Introl, Serverless GPU Platforms: RunPod, Modal, and Beam Compared (2025)
https://introl.com/blog/serverless-gpu-platforms-runpod-modal-beam-comparison-guide-2025

[10] RunPod Documentation, Serverless Endpoint Configurations
https://docs.runpod.io/serverless/endpoints/endpoint-configurations

[11] LTX Blog, How To Generate 20 Second AI Videos With LTX-2.3
https://ltx.io/model/model-blog/how-to-generate-20-second-ai-videos

[12] GitHub, thu-ml/SageAttention (ICLR/ICML/NeurIPS 2025)
https://github.com/thu-ml/sageattention

[13] arXiv 2505.21136, SageAttention2++: A More Efficient Implementation
https://arxiv.org/abs/2505.21136

[14] LTX Workflow, LTX 2.3 FP16 vs FP8 vs GGUF: Which Format to Choose
https://ltxworkflow.com/blog/fp16-vs-fp8-vs-gguf-which-ltx-23-format-to-choose

[15] GitHub, Comfy-Org/ComfyUI Issue #11864: Native NVFP4 Loading Failure on RTX 5090
https://github.com/Comfy-Org/ComfyUI/issues/11864

[16] WaveSpeed, LTX-2.3 Pricing: API Cost, Local Inference & Cloud Trade-offs (2026)
https://wavespeed.ai/blog/posts/ltx-2-3-pricing-api-cost-2026/

[17] PyTorch Blog, Faster Diffusion on Blackwell: MXFP8 and NVFP4 with Diffusers and TorchAO
https://pytorch.org/blog/faster-diffusion-on-blackwell-mxfp8-and-nvfp4-with-diffusers-and-torchao/

[18] WaveSpeed, LTX-2.3: What's New in Lightricks' 22B Video Model (2026)
https://wavespeed.ai/blog/posts/ltx-2-3-whats-new-2026/

[19] GitHub, Wan-Video/Wan2.2 Official Repository
https://github.com/Wan-Video/Wan2.2

[20] Artificial Analysis, Wan 2.5 Benchmark Debut (closed weights, API-only)
https://x.com/ArtificialAnlys/status/1977910656566489143

[21] WaveSpeed, Wan 2.7 Is Coming: A Major All-Around Upgrade Over 2.6
https://wavespeed.ai/blog/posts/wan-2-7-coming-soon-major-upgrade/

[22] Introl, Spot Instances and Preemptible GPUs: Cutting AI Costs by 70%
https://introl.com/blog/spot-instances-preemptible-gpus-ai-cost-savings

[23] Vast.ai, On Demand vs Interruptible Rental Types
https://vast.ai/article/Rental-Types

[24] arXiv 2509.24006, SLA: Beyond Sparsity in Diffusion Transformers via Fine-Tunable Sparse-Linear Attention
https://arxiv.org/pdf/2509.24006

[25] WaveSpeed, LTX-2 VRAM Requirements: 12GB vs 24GB Reality Check
https://wavespeed.ai/blog/posts/blog-ltx-2-vram-requirements/

[26] Novita, Wan 2.2 VRAM: Find the Best GPU Setup for Deployment
https://blogs.novita.ai/wan-2-2-vram-find-the-best-gpu-setup-for-deployment/

[27] RunPod, RTX 5090 Specs and VRAM: Specifications, AI Benchmarks
https://www.runpod.io/articles/guides/nvidia-rtx-5090

[28] RunPod, RTX 4090 vs L40S GPU Benchmarks
https://www.runpod.io/gpu-compare/rtx-4090-vs-l40s

[29] Voltage Park, Accelerating Wan2.2: From 4.67s to 1.5s Per Denoising Step
https://www.voltagepark.com/blog/accelerating-wan2-2-from-4-67s-to-1-5s-per-denoising-step-through-targeted-optimizations

[30] Koyeb, Serverless GPUs: RTX Pro 6000, H200, and B200 Now Available
https://www.koyeb.com/blog/koyeb-serverless-gpus-launch-rtx-pro-6000-h200-B200

[31] RunPod, GPU Cloud Pricing
https://www.runpod.io/pricing

[32] Vast.ai, Rent RTX 5090 GPUs
https://vast.ai/pricing/gpu/RTX-5090

[33] Novita AI, Rent Cheap A100 and H100
https://blogs.novita.ai/rent-cheap-a100-and-h100-boost-training-efficiency-with-novita-ai/

[34] Spheron, GPU Cloud Pricing 2026: H100 from $1.03/hr
https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/

[35] RunPod Documentation, Serverless Pricing
https://docs.runpod.io/serverless/pricing

[36] GitHub, runpod-workers/worker-vllm Issue #111: Very Slow Cold Starts Even With FlashBoot
https://github.com/runpod-workers/worker-vllm/issues/111

[37] Modal, Plan Pricing
https://modal.com/pricing

[38] Modal Docs, Cold Start Performance
https://modal.com/docs/guide/cold-start

[39] APIScout, fal.ai vs Replicate vs Modal in 2026
https://apiscout.dev/guides/fal-ai-vs-replicate-vs-modal-2026

[40] CheckThat.ai, Replicate Pricing 2026
https://checkthat.ai/brands/replicate/pricing

[41] Markaicode, RunPod Pricing: Real Costs for Production Workloads
https://markaicode.com/pricing/runpod-pricing-gpu-pod-production/

[42] Vast.ai Documentation, Instance Types
https://docs.vast.ai/documentation/instances/choosing/instance-types

[43] SaladCloud Docs, Container Engine FAQs
https://docs.salad.com/container-engine/explanation/core-concepts/faqs

[44] arXiv 2410.02367, SageAttention: Accurate 8-Bit Attention for Plug-and-play Inference Acceleration
https://arxiv.org/abs/2410.02367

[45] arXiv 2505.11594, SageAttention3: Microscaling FP4 Attention
https://arxiv.org/abs/2505.11594

[46] arXiv 2411.05007, SVDQuant: Absorbing Outliers by Low-Rank Components for 4-Bit Diffusion Models
https://arxiv.org/abs/2411.05007

[47] MIT HAN Lab, SVDQuant Project Page
https://hanlab.mit.edu/projects/svdquant

[48] DeepWiki, Nunchaku Hardware Compatibility and Precision Selection
https://deepwiki.com/mit-han-lab/nunchaku/1.2-hardware-compatibility-and-precision-selection

[49] GitHub, vladmandic/sdnext Wiki: Quantization
https://github.com/vladmandic/sdnext/wiki/Quantization

[50] Stable Diffusion Art, TeaCache: 2x Speed Up in ComfyUI
https://stable-diffusion-art.com/teacache/

[51] DeepWiki, kijai/ComfyUI-WanVideoWrapper: Block Swapping and Device Management
https://deepwiki.com/kijai/ComfyUI-WanVideoWrapper/6.2-block-swapping-and-device-management

[52] arXiv 2506.04648, FPSAttention: Training-Aware FP8 and Sparsity Co-Design for Fast Video Diffusion
https://arxiv.org/abs/2506.04648

[53] GitHub, mobcat40/sageattention-blackwell (prebuilt wheel)
https://github.com/mobcat40/sageattention-blackwell

[54] GMI Cloud, GPU vs CPU Inference: Speed, Cost & Scale
https://www.gmicloud.ai/en/blog/gpu-inference-vs-cpu-inference-speed-cost-and-scalability
