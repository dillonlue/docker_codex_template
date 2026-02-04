args <- commandArgs(trailingOnly = TRUE)

parse_args <- function(args) {
  res <- list()
  i <- 1
  while (i <= length(args)) {
    if (grepl("^--", args[i])) {
      key <- sub("^--", "", args[i])
      if (i + 1 <= length(args)) {
        res[[key]] <- args[i + 1]
      }
      i <- i + 2
    } else {
      i <- i + 1
    }
  }
  res
}

`%||%` <- function(a, b) {
  if (is.null(a) || is.na(a) || a == "") b else a
}

opts <- parse_args(args)
train_tsv <- opts[["train-tsv"]]
out_summary <- opts[["out-summary"]]
out_pvals <- opts[["out-pvals"]]
num_pcs <- as.integer(opts[["num-pcs"]] %||% "10")
jackstraw_s <- as.integer(opts[["jackstraw-s"]] %||% "100")
jackstraw_b <- as.integer(opts[["jackstraw-b"]] %||% "200")
seed <- as.integer(opts[["seed"]] %||% "123")

if (is.null(train_tsv) || is.null(out_summary) || is.null(out_pvals)) {
  stop("Missing required arguments: --train-tsv, --out-summary, --out-pvals")
}

if (!requireNamespace("jackstraw", quietly = TRUE)) {
  install.packages("jackstraw", repos = "https://cloud.r-project.org")
}

if (!requireNamespace("jackstraw", quietly = TRUE)) {
  stop("jackstraw package is required but not available after install")
}

set.seed(seed)
X <- as.matrix(read.delim(train_tsv, header = FALSE))

# Use pixels as variables (rows) and images as samples (columns).
X_for_js <- t(X)

max_pcs <- min(dim(X_for_js)) - 1L
if (num_pcs > max_pcs) {
  num_pcs <- max_pcs
}

fn <- NULL
fn_name <- NULL
candidates <- c("jackstraw_pca", "jackstraw")
for (name in candidates) {
  if (exists(name, where = asNamespace("jackstraw"), inherits = FALSE)) {
    fn <- get(name, envir = asNamespace("jackstraw"))
    fn_name <- name
    break
  }
}
if (is.null(fn)) {
  stop("Could not find a jackstraw function to run")
}

fmls <- names(formals(fn))
args_list <- list()
if ("dat" %in% fmls) {
  args_list$dat <- X_for_js
} else if ("data" %in% fmls) {
  args_list$data <- X_for_js
} else if ("X" %in% fmls) {
  args_list$X <- X_for_js
} else if ("x" %in% fmls) {
  args_list$x <- X_for_js
} else {
  stop("Unable to determine data argument name for jackstraw")
}

if ("r" %in% fmls) {
  args_list$r <- num_pcs
} else if ("k" %in% fmls) {
  args_list$k <- num_pcs
}
if ("s" %in% fmls) {
  args_list$s <- jackstraw_s
}
if ("B" %in% fmls) {
  args_list$B <- jackstraw_b
} else if ("num.iter" %in% fmls) {
  args_list$num.iter <- jackstraw_b
}

res <- do.call(fn, args_list)

extract_pvals <- function(obj) {
  if (is.list(obj)) {
    for (name in c("p.value", "p.values", "p.vals", "pvals")) {
      if (!is.null(obj[[name]])) {
        return(obj[[name]])
      }
    }
  }
  if (isS4(obj)) {
    for (name in c("p.value", "p.values", "p.vals", "pvals")) {
      if (name %in% slotNames(obj)) {
        return(slot(obj, name))
      }
    }
  }
  NULL
}

pvals <- extract_pvals(res)
summary_df <- data.frame(
  key = c(
    "n_samples",
    "n_features",
    "num_pcs",
    "jackstraw_s",
    "jackstraw_b",
    "jackstraw_function",
    "seed"
  ),
  value = c(
    ncol(X_for_js),
    nrow(X_for_js),
    num_pcs,
    jackstraw_s,
    jackstraw_b,
    fn_name,
    seed
  ),
  stringsAsFactors = FALSE
)

pvals_vec <- NULL
if (!is.null(pvals)) {
  pvals_vec <- as.numeric(pvals)
  pvals_vec <- pvals_vec[is.finite(pvals_vec)]
  if (length(pvals_vec) > 0) {
    extra <- data.frame(
      key = c("pvals_min", "pvals_median", "pvals_mean", "pvals_count"),
      value = c(
        min(pvals_vec),
        median(pvals_vec),
        mean(pvals_vec),
        length(pvals_vec)
      ),
      stringsAsFactors = FALSE
    )
    summary_df <- rbind(summary_df, extra)
  }
}

summary_dir <- dirname(out_summary)
if (!dir.exists(summary_dir)) {
  dir.create(summary_dir, recursive = TRUE)
}
write.table(summary_df, out_summary, sep = "\t", row.names = FALSE, quote = FALSE)

pvals_dir <- dirname(out_pvals)
if (!dir.exists(pvals_dir)) {
  dir.create(pvals_dir, recursive = TRUE)
}

if (!is.null(pvals)) {
  pmat <- as.matrix(pvals)
  pvals_df <- data.frame(
    feature = rep(seq_len(nrow(pmat)), times = ncol(pmat)),
    pc = rep(seq_len(ncol(pmat)), each = nrow(pmat)),
    p_value = as.vector(pmat),
    stringsAsFactors = FALSE
  )
  write.table(pvals_df, out_pvals, sep = "\t", row.names = FALSE, quote = FALSE)
} else {
  pvals_df <- data.frame(feature = integer(), pc = integer(), p_value = numeric())
  write.table(pvals_df, out_pvals, sep = "\t", row.names = FALSE, quote = FALSE)
}
